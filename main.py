import asyncio
import logging
import os
import re
import time
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

import requests
import schedule
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://jack@localhost:5432/price_tracker")
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database reset complete!")


# Models
class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    current_price = Column(Float)
    target_price = Column(Float)
    lowest_price = Column(Float)
    highest_price = Column(Float)
    last_checked = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String, index=True)
    store = Column(String, default="amazon")  # Added store field to track which marketplace

class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, index=True)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

def check_and_update_schema():
    """Check if store column exists and add it if missing"""
    from sqlalchemy import inspect, text
    
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('products')]
    
    if 'store' not in columns:
        logger.info("Adding missing 'store' column to products table...")
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE products ADD COLUMN store VARCHAR DEFAULT 'amazon'"))
            conn.commit()
        logger.info("Schema update complete!")

# Call this function before creating tables
check_and_update_schema()

Base.metadata.create_all(bind=engine)

# Pydantic models
class ProductCreate(BaseModel):
    name: str
    url: HttpUrl
    target_price: float
    user_id: str

class ProductResponse(BaseModel):
    id: int
    name: str
    url: str
    current_price: Optional[float]
    target_price: float
    lowest_price: Optional[float]
    highest_price: Optional[float]
    last_checked: Optional[datetime]
    is_active: bool
    created_at: datetime
    store: str

class PriceAlert(BaseModel):
    product_id: int
    product_name: str
    current_price: float
    target_price: float
    url: str

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# Base scraper class
class BaseScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        }
        self.session.headers.update(self.headers)
    
    def extract_price(self, text: str) -> Optional[float]:
        """Extract numeric price from text"""
        if not text:
            return None
            
        # Remove currency symbols, commas, and other non-numeric characters
        price_text_clean = re.sub(r'[₹$€£¥,\s]', '', text)
        price_match = re.search(r'[\d]+\.?\d*', price_text_clean)
        
        if price_match:
            return float(price_match.group())
        return None

# Amazon scraper class
class AmazonScraper(BaseScraper):
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Extract product information from Amazon URL"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract product name
            name_selectors = [
                '#productTitle',
                '.product-title',
                'h1.a-size-large',
                'h1.a-size-base-plus'
            ]
            
            name = None
            for selector in name_selectors:
                element = soup.select_one(selector)
                if element:
                    name = element.get_text().strip()
                    break
            
            # Extract price - Updated selectors for the new structure
            price_selectors = [
                '.a-price.priceToPay .a-price-whole',
                '.a-price.reinventPricePriceToPayMargin .a-price-whole',
                '.a-price.aok-align-center .a-price-whole',
                '.a-price .a-price-whole',
                '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
                '.a-price-whole',
                '.a-price .a-offscreen',
                '.priceBlockBuyingPriceString',
                '.priceBlockDealPriceString',
                'span.a-price-range'
            ]
            
            price = None
            for selector in price_selectors:
                element = soup.select_one(selector)
                if element:
                    price_text = element.get_text().strip()
                    price = self.extract_price(price_text)
                    if price:
                        break
            
            # If price_whole didn't work, try getting from price symbol + whole combination
            if price is None:
                price_container = soup.select_one('.a-price.priceToPay') or soup.select_one('.a-price.reinventPricePriceToPayMargin')
                if price_container:
                    price_whole = price_container.select_one('.a-price-whole')
                    price_fraction = price_container.select_one('.a-price-fraction')
                    
                    if price_whole:
                        whole_text = price_whole.get_text().strip()
                        fraction_text = price_fraction.get_text().strip() if price_fraction else "00"
                        
                        # Combine whole and fraction parts
                        try:
                            price = float(f"{whole_text}.{fraction_text}")
                        except ValueError:
                            # Fallback to just whole number
                            price = self.extract_price(whole_text)
            
            logger.info(f"Scraped Amazon product: {name}, Price: {price}")
            
            return {
                'name': name,
                'price': price,
                'success': True
            }
            
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Parsing error for {url}: {e}")
            return {'success': False, 'error': str(e)}
    
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is a valid Amazon product URL"""
        parsed = urlparse(url)
        return 'amazon' in parsed.netloc and '/dp/' in parsed.path

# Flipkart scraper class
import random
import time
from fake_useragent import UserAgent

# Add to your imports at the top
import cloudscraper  # For bypassing Cloudflare protection

# Update your FlipkartScraper class
class FlipkartScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        # Use cloudscraper to bypass Cloudflare protection
        self.scraper = cloudscraper.create_scraper()
        self.ua = UserAgent()
        self.set_random_headers()
    
    def set_random_headers(self):
        """Set random headers to avoid detection"""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'TE': 'trailers',
        }
        self.scraper.headers.update(self.headers)
    
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Extract product information from Flipkart URL with retries"""
        max_retries = 3
        attempt = 0
        name, price, old_price, discount, reviews = None, None, None, None, None

        while attempt < max_retries and not (name and price):
            try:
                time.sleep(random.uniform(2, 5))  # random delay
                self.set_random_headers()  # rotate headers each attempt
                response = self.scraper.get(url, timeout=15)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')

                # Product name
                name_selectors = [
                    'h1._6EBuvT span.VU-ZEz',
                    'span.VU-ZEz',
                    'h1._6EBuvT',
                    'span.B_NuCI',
                    'h1.yhB1nd',
                    'h1._2Kn22P',
                ]
                for selector in name_selectors:
                    element = soup.select_one(selector)
                    if element:
                        name = element.get_text(strip=True)
                        break

                # Price
                price_selectors = [
                    'div.Nx9bqj.CxhGGd',   # new Flipkart structure
                    'div._30jeq3._16Jk6d',
                    'div._30jeq3._1_WHN1',
                ]
                for selector in price_selectors:
                    element = soup.select_one(selector)
                    if element:
                        price = self.extract_price(element.get_text(strip=True))
                        if price:
                            break

                # Old price
                old_price_el = soup.select_one('div.yRaY8j.A6+E6v')
                if old_price_el:
                    old_price = self.extract_price(old_price_el.get_text(strip=True))

                # Discount
                discount_el = soup.select_one('div.UkUFwK.WW8yVX span')
                if discount_el:
                    discount = discount_el.get_text(strip=True)

                # Reviews
                reviews_el = soup.select_one('span.Wphh3N')
                if reviews_el:
                    reviews = reviews_el.get_text(strip=True)

                if name and price:
                    logger.info(f"✅ Scraped Flipkart product (attempt {attempt+1}): {name} - {price}")
                    return {
                        'name': name,
                        'price': price,
                        'old_price': old_price,
                        'discount': discount,
                        'reviews': reviews,
                        'success': True
                    }

            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt+1} failed for {url}: {e}")

            attempt += 1

        logger.error(f"❌ Failed to scrape Flipkart product after {max_retries} attempts: {url}")
        return {'success': False, 'error': 'Unable to fetch product details after retries'}

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is a valid Flipkart product URL"""
        parsed = urlparse(url)
        return 'flipkart.com' in parsed.netloc and ('/p/' in parsed.path or '/product/' in parsed.path)
# Scraper factory
class ScraperFactory:
    @staticmethod
    def get_scraper(url: str) -> BaseScraper:
        """Get appropriate scraper based on URL"""
        if 'amazon' in url:
            return AmazonScraper()
        elif 'flipkart' in url:
            return FlipkartScraper()
        else:
            raise ValueError(f"Unsupported store URL: {url}")
    
    @staticmethod
    def get_store_name(url: str) -> str:
        """Get store name from URL"""
        if 'amazon' in url:
            return "amazon"
        elif 'flipkart' in url:
            return "flipkart"
        else:
            return "unknown"

# Telegram notification service
class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
    
    async def send_price_alert(self, alert: PriceAlert):
        """Send price alert to Telegram"""
        try:
            # Determine currency symbol based on URL
            currency = "₹" if any(x in alert.url for x in ["amazon.in", "flipkart.com"]) else "$"
            
            message = f"🚨 *PRICE ALERT!* 🚨\n\n"
            message += f"📦 *Product:* {alert.product_name[:50]}...\n\n"
            message += f"💰 *Current Price:* {currency}{alert.current_price:.2f}\n"
            message += f"🎯 *Your Target:* {currency}{alert.target_price:.2f}\n"
            message += f"💸 *You Save:* {currency}{abs(alert.target_price - alert.current_price):.2f}\n\n"
            message += f"🔗 [🛒 BUY NOW]({alert.url})\n\n"
            message += f"⏰ *Alert Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            logger.info(f"✅ Alert sent for product: {alert.product_name}")
            
        except TelegramError as e:
            logger.error(f"❌ Failed to send Telegram alert: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error sending alert: {e}")

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Background task functions
def check_all_prices_sync():
    """Synchronous wrapper for price checking"""
    db = SessionLocal()
    try:
        asyncio.run(check_all_prices(db))
    except Exception as e:
        logger.error(f"Error in scheduled price check: {e}")
    finally:
        db.close()

async def check_all_prices(db: Session):
    """Check prices for all active products"""
    products = db.query(Product).filter(Product.is_active == True).all()
    
    logger.info(f"🔍 Checking prices for {len(products)} active products...")
    
    alerts_sent = 0
    for product in products:
        try:
            logger.info(f"Checking: {product.name}")
            
            # Get appropriate scraper for the product's store
            scraper = ScraperFactory.get_scraper(product.url)
            product_info = scraper.get_product_info(product.url)
            
            if product_info['success'] and product_info['price']:
                old_price = product.current_price
                new_price = product_info['price']
                
                # Update product record
                product.current_price = new_price
                product.last_checked = datetime.utcnow()
                
                # Update price bounds
                if not product.lowest_price or new_price < product.lowest_price:
                    product.lowest_price = new_price
                if not product.highest_price or new_price > product.highest_price:
                    product.highest_price = new_price
                
                db.commit()
                
                # Add to price history
                price_history = PriceHistory(
                    product_id=product.id,
                    price=new_price
                )
                db.add(price_history)
                db.commit()
                
                # Check if price alert should be sent
                if new_price <= product.target_price:
                    alert = PriceAlert(
                        product_id=product.id,
                        product_name=product.name,
                        current_price=new_price,
                        target_price=product.target_price,
                        url=product.url
                    )
                    await notifier.send_price_alert(alert)
                    alerts_sent += 1
                
                if old_price != new_price:
                    logger.info(f"💰 Price updated for {product.name}: {old_price} -> {new_price}")
                else:
                    logger.info(f"📊 Price unchanged for {product.name}: {new_price}")
                    
            else:
                logger.warning(f"⚠️ Failed to get price for {product.name}: {product_info.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"❌ Error checking price for {product.name}: {e}")
        
        # Add delay to avoid being blocked (2-5 seconds random)
        import random
        delay = random.uniform(2, 5)
        time.sleep(delay)
    
    logger.info(f"✅ Price check completed! Sent {alerts_sent} alerts.")

# Schedule price checks
def schedule_price_checks():
    """Schedule regular price checks"""
    # Schedule every hour
    schedule.every().hour.do(check_all_prices_sync)
    # Optional: Also schedule at specific times for more frequent checks
    schedule.every().day.at("09:00").do(check_all_prices_sync)
    schedule.every().day.at("15:00").do(check_all_prices_sync)
    schedule.every().day.at("21:00").do(check_all_prices_sync)
    
    logger.info("📅 Scheduled price checks: Every hour + 9AM, 3PM, 9PM daily")

def run_scheduler():
    """Run the scheduler in a background thread"""
    logger.info("🚀 Starting background scheduler...")
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(60)

# FastAPI app
app = FastAPI(
    title="E-Commerce Price Tracker API",
    description="Track product prices from Amazon, Flipkart and get automated notifications",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

# API Routes
@app.get("/")
async def root():
    return {
        "message": "E-Commerce Price Tracker API with Automated Alerts", 
        "version": "2.1.0",
        "features": ["Amazon & Flipkart support", "Automated hourly checks", "Telegram notifications", "Price history tracking"],
        "status": "🟢 Running",
        "supported_stores": ["Amazon", "Flipkart"]
    }

@app.post("/products/", response_model=ProductResponse)
async def add_product(product: ProductCreate, db: Session = Depends(get_db)):
    """Add a new product to track"""
    
    # Get appropriate scraper and validate URL
    try:
        scraper = ScraperFactory.get_scraper(str(product.url))
        if not scraper.is_valid_url(str(product.url)):
            raise HTTPException(status_code=400, detail="Invalid product URL for this store")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check if product already exists
    existing = db.query(Product).filter(Product.url == str(product.url)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Product already being tracked")
    
    # Get initial product info
    logger.info(f"Fetching info for new product: {product.url}")
    product_info = scraper.get_product_info(str(product.url))
    if not product_info['success']:
        raise HTTPException(status_code=400, detail=f"Failed to fetch product info: {product_info.get('error', 'Unknown error')}")
    
    # Determine store name
    store = ScraperFactory.get_store_name(str(product.url))
    
    # Create product record
    db_product = Product(
        name=product.name or product_info['name'],
        url=str(product.url),
        current_price=product_info['price'],
        target_price=product.target_price,
        lowest_price=product_info['price'],
        highest_price=product_info['price'],
        last_checked=datetime.utcnow(),
        user_id=product.user_id,
        store=store
    )
    
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    
    # Add to price history
    price_history = PriceHistory(
        product_id=db_product.id,
        price=product_info['price']
    )
    db.add(price_history)
    db.commit()
    
    logger.info(f"✅ Added product: {db_product.name} (Current: {product_info['price']}, Target: {product.target_price}, Store: {store})")
    return db_product

@app.get("/products/", response_model=List[ProductResponse])
async def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all tracked products"""
    products = db.query(Product).offset(skip).limit(limit).all()
    return products

@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a specific product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.delete("/products/{product_id}")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete a product from tracking"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    db.delete(product)
    db.commit()
    logger.info(f"🗑️ Deleted product: {product.name}")
    return {"message": "Product deleted successfully"}

@app.post("/products/{product_id}/toggle")
async def toggle_product(product_id: int, db: Session = Depends(get_db)):
    """Toggle product active status"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.is_active = not product.is_active
    db.commit()
    status = "activated" if product.is_active else "deactivated"
    logger.info(f"📊 Product {status}: {product.name}")
    return {"message": f"Product {status}"}

@app.get("/products/{product_id}/history")
async def get_price_history(product_id: int, days: int = 30, db: Session = Depends(get_db)):
    """Get price history for a product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    since_date = datetime.utcnow() - timedelta(days=days)
    history = db.query(PriceHistory).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.timestamp >= since_date
    ).order_by(PriceHistory.timestamp.desc()).all()
    
    return {
        "product_id": product_id,
        "product_name": product.name,
        "history": [{"price": h.price, "timestamp": h.timestamp} for h in history],
        "total_records": len(history)
    }

@app.post("/check-prices")
async def manual_price_check(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger price check for all products"""
    logger.info("🔍 Manual price check triggered")
    background_tasks.add_task(check_all_prices, db)
    return {"message": "Price check started", "status": "running"}

@app.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status"""
    return {
        "scheduler_running": True,
        "next_runs": [str(job.next_run) for job in schedule.jobs] if schedule.jobs else [],
        "total_jobs": len(schedule.jobs),
        "check_frequency": "Every hour + 3 daily checks"
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 E-Commerce Price Tracker API with Automated Alerts starting...")
    
    # Schedule price checks
    schedule_price_checks()
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    logger.info("✅ Background scheduler started successfully!")
    logger.info("🔔 Automated alerts are now active!")
    logger.info("🛍️ Supported stores: Amazon, Flipkart")

# Health check endpoint
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    active_products = db.query(Product).filter(Product.is_active == True).count()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "database": "connected",
        "active_products": active_products,
        "scheduler": "running",
        "alerts": "enabled",
        "supported_stores": ["Amazon", "Flipkart"]
    }

# Statistics endpoint
@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get tracking statistics"""
    total_products = db.query(Product).count()
    active_products = db.query(Product).filter(Product.is_active == True).count()
    total_price_checks = db.query(PriceHistory).count()
    
    # Count by store
    amazon_products = db.query(Product).filter(Product.store == "amazon").count()
    flipkart_products = db.query(Product).filter(Product.store == "flipkart").count()
    
    # Recent activity (last 24 hours)
    since_yesterday = datetime.utcnow() - timedelta(days=1)
    recent_checks = db.query(PriceHistory).filter(PriceHistory.timestamp >= since_yesterday).count()
    
    return {
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": total_products - active_products,
        "amazon_products": amazon_products,
        "flipkart_products": flipkart_products,
        "other_stores": total_products - amazon_products - flipkart_products,
        "total_price_checks": total_price_checks,
        "recent_checks_24h": recent_checks,
        "scheduler_jobs": len(schedule.jobs),
        "last_updated": datetime.utcnow()
    }

if __name__ == "__main__":
    import uvicorn
    reset_database()  # Add this line
    logger.info("🚀 Starting E-Commerce Price Tracker with Automated Alerts...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin, urlparse

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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = "postgresql+psycopg2://jack@localhost:5432/price_tracker"
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, index=True)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

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

class PriceAlert(BaseModel):
    product_id: int
    product_name: str
    current_price: float
    target_price: float
    url: str

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# Amazon scraper class
class AmazonScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.session.headers.update(self.headers)
    
    def get_product_info(self, url: str) -> dict:
        """Extract product information from Amazon URL"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract product name
            name_selectors = [
                '#productTitle',
                '.product-title',
                'h1.a-size-large'
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
                '.priceBlockDealPriceString'
            ]
            
            price = None
            for selector in price_selectors:
                element = soup.select_one(selector)
                if element:
                    price_text = element.get_text().strip()
                    # Remove currency symbols and commas, extract numeric value
                    price_text_clean = re.sub(r'[₹$€£¥,]', '', price_text)
                    price_match = re.search(r'[\d]+\.?\d*', price_text_clean)
                    if price_match:
                        price = float(price_match.group())
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
                            price_match = re.search(r'[\d,]+', whole_text.replace(',', ''))
                            if price_match:
                                price = float(price_match.group())
            
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
    
    def is_valid_amazon_url(self, url: str) -> bool:
        """Check if URL is a valid Amazon product URL"""
        parsed = urlparse(url)
        return 'amazon' in parsed.netloc and '/dp/' in parsed.path
    
# Telegram notification service
class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
    
    async def send_price_alert(self, alert: PriceAlert):
        """Send price alert to Telegram"""
        try:
            message = f"🚨 *Price Alert!*\n\n"
            message += f"📦 *Product:* {alert.product_name}\n"
            message += f"💰 *Current Price:* ${alert.current_price:.2f}\n"
            message += f"🎯 *Target Price:* ${alert.target_price:.2f}\n"
            message += f"🔗 [View Product]({alert.url})"
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            logger.info(f"Alert sent for product {alert.product_name}")
            
        except TelegramError as e:
            logger.error(f"Failed to send Telegram alert: {e}")

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI app
app = FastAPI(
    title="Amazon Price Tracker API",
    description="Track Amazon product prices and get notifications",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
scraper = AmazonScraper()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

# API Routes
@app.get("/")
async def root():
    return {"message": "Amazon Price Tracker API", "version": "1.0.0"}

@app.post("/products/", response_model=ProductResponse)
async def add_product(product: ProductCreate, db: Session = Depends(get_db)):
    """Add a new product to track"""
    
    # Validate Amazon URL
    if not scraper.is_valid_amazon_url(str(product.url)):
        raise HTTPException(status_code=400, detail="Invalid Amazon URL")
    
    # Check if product already exists
    existing = db.query(Product).filter(Product.url == str(product.url)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Product already being tracked")
    
    # Get initial product info
    product_info = scraper.get_product_info(str(product.url))
    if not product_info['success']:
        raise HTTPException(status_code=400, detail=f"Failed to fetch product info: {product_info.get('error', 'Unknown error')}")
    
    # Create product record
    db_product = Product(
        name=product.name or product_info['name'],
        url=str(product.url),
        current_price=product_info['price'],
        target_price=product.target_price,
        lowest_price=product_info['price'],
        highest_price=product_info['price'],
        last_checked=datetime.utcnow(),
        user_id=product.user_id
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
    
    logger.info(f"Added product: {db_product.name}")
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
    return {"message": "Product deleted successfully"}

@app.post("/products/{product_id}/toggle")
async def toggle_product(product_id: int, db: Session = Depends(get_db)):
    """Toggle product active status"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.is_active = not product.is_active
    db.commit()
    return {"message": f"Product {'activated' if product.is_active else 'deactivated'}"}

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
        "history": [{"price": h.price, "timestamp": h.timestamp} for h in history]
    }

@app.post("/check-prices")
async def manual_price_check(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger price check for all products"""
    background_tasks.add_task(check_all_prices, db)
    return {"message": "Price check started"}

# Background task functions
async def check_all_prices(db: Session):
    """Check prices for all active products"""
    products = db.query(Product).filter(Product.is_active == True).all()
    
    logger.info(f"Checking prices for {len(products)} products")
    
    for product in products:
        try:
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
                
                logger.info(f"Updated {product.name}: ${old_price} -> ${new_price}")
                
        except Exception as e:
            logger.error(f"Error checking price for {product.name}: {e}")
        
        # Add delay to avoid being blocked
        time.sleep(2)

# Schedule price checks
def schedule_price_checks():
    """Schedule regular price checks"""
    schedule.every(1).hours.do(lambda: asyncio.create_task(check_all_prices(SessionLocal())))

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Amazon Price Tracker API started")
    schedule_price_checks()

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "database": "connected"
    }

# Statistics endpoint
@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get tracking statistics"""
    total_products = db.query(Product).count()
    active_products = db.query(Product).filter(Product.is_active == True).count()
    total_price_checks = db.query(PriceHistory).count()
    
    return {
        "total_products": total_products,
        "active_products": active_products,
        "total_price_checks": total_price_checks,
        "last_updated": datetime.utcnow()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

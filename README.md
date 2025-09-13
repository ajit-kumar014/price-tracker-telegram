# Amazon_Flipkart Price Tracker API

A robust, scalable price tracking system built with FastAPI, capable of monitoring 1000+ Amazon_Flipkart products with automated notifications through Telegram.

![Python](https://img.shields.io/badge/python-v3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## 🚀 Features

- **High-Performance API**: Built with FastAPI for async operations and auto-generated documentation
- **Scalable Architecture**: Handle 1000+ products efficiently with optimized database queries
- **Automated Scraping**: Intelligent Amazon_Flipkart price extraction using BeautifulSoup with anti-bot measures
- **Smart Notifications**: Telegram bot integration for instant price drop alerts
- **Price History**: Complete historical price tracking with trend analysis
- **Docker Ready**: Containerized for easy homelab deployment
- **RESTful API**: Full CRUD operations with OpenAPI documentation
- **Background Processing**: Automated hourly price checks with manual triggers

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#️-installation)
- [Configuration](#️-configuration)
- [API Documentation](#-api-documentation)
- [Docker Deployment](#-docker-deployment)
- [Usage Examples](#-usage-examples)
- [Monitoring](#-monitoring)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

## 🏁 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional)
- Telegram Bot Token
- Telegram Chat ID

### 1. Telegram Bot Setup
Check this out this will be helpfull:
[](https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a)

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot: `/newbot`
3. Follow instructions and save your **Bot Token**
4. Start a chat with your bot and send any message
5. Get your **Chat ID** by visiting:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   Look for `"chat":{"id":<YOUR_CHAT_ID>}` in the response

### 2. Quick Docker Start (make sure port 8000 and 5432 are not used otherwise change the ports in the docker compose file)

```bash
# Clone the repository
git clone https://github.com/yourusername/Amazon_Flipkart-price-tracker.git
cd Amazon_Flipkart-price-tracker

# Make app directory
mkdir app

# Make docker image using docker build
docker build -t app .

# Configure environment
nano .env
# Edit .env with your Telegram credentials

# Start the application
docker-compose up -d

# Check if it's running
curl http://localhost:8000/health

Access all functionality at localhost:8000/docs or IP_ADDRESS:8000/docs from any device in the local network.
```

Your API will be available at `http://localhost:8000` with documentation at `http://localhost:8000/docs`

## ⚙️ Installation

### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/Amazon_Flipkart-price-tracker.git
cd Amazon_Flipkart-price-tracker

# Making docker image from DockerFile.
docker built -t app .

# Create environment file
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
EOF

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

## 🛠️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
TELEGRAM_CHAT_ID=123456789

# Optional Configuration
DATABASE_URL="postgresql+psycopg2://jack@localhost:5432/price_tracker"
LOG_LEVEL=INFO
```

### File Structure

```
Amazon_Flipkart-price-tracker/
├── main.py                 # Main application file
├── requirements.txt        # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
├── .env.example          # Environment template
├── .env                  # Your environment variables (create this)
├── .dockerignore         # Docker ignore rules
├── README.md             # This file
├── data/                 # Database storage (created automatically)
└── logs/                 # Application logs (created automatically)
```

## 📚 API Documentation

### Base URL
```
http://localhost:8000
```

### Interactive Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API information |
| `POST` | `/products/` | Add new product to track |
| `GET` | `/products/` | List all tracked products |
| `GET` | `/products/{id}` | Get specific product details |
| `DELETE` | `/products/{id}` | Remove product from tracking |
| `POST` | `/products/{id}/toggle` | Toggle product active status |
| `GET` | `/products/{id}/history` | Get price history |
| `POST` | `/check-prices` | Manual price check trigger |
| `GET` | `/health` | Health check |
| `GET` | `/stats` | System statistics |

### Resource Requirements

- **Memory**: 256MB minimum, 512MB recommended
- **CPU**: 1 core sufficient for 1000+ products
- **Storage**: 1GB for database and logs
- **Network**: Outbound HTTPS access required

## 💡 Usage Examples

### Add a Product

```bash
curl -X POST "http://localhost:8000/products/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "iPhone 15 Pro",
    "url": "https://www.Amazon_Flipkart.com/dp/B0CHX1W1XY",
    "target_price": 899.99,
    "user_id": "user123"
  }'
```

### List All Products

```bash
curl -X GET "http://localhost:8000/products/"
```

### Get Product Price History

```bash
curl -X GET "http://localhost:8000/products/1/history?days=30"
```

### Trigger Manual Price Check

```bash
curl -X POST "http://localhost:8000/check-prices"
```

### Delete a Product

```bash
curl -X DELETE "http://localhost:8000/products/1"
```

### Python Client Example

```python
import requests

class PriceTrackerClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def add_product(self, name, url, target_price, user_id):
        data = {
            "name": name,
            "url": url,
            "target_price": target_price,
            "user_id": user_id
        }
        response = requests.post(f"{self.base_url}/products/", json=data)
        return response.json()
    
    def get_products(self):
        response = requests.get(f"{self.base_url}/products/")
        return response.json()
    
    def check_prices(self):
        response = requests.post(f"{self.base_url}/check-prices")
        return response.json()

# Usage
client = PriceTrackerClient()
client.add_product(
    name="Gaming Laptop",
    url="https://www.Amazon_Flipkart.com/dp/PRODUCTID",
    target_price=1200.00,
    user_id="user123"
)
```

## 📊 Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-08-24T10:30:00.000Z",
  "database": "connected"
}
```

### System Statistics

```bash
curl http://localhost:8000/stats
```

Response:
```json
{
  "total_products": 150,
  "active_products": 142,
  "total_price_checks": 5847,
  "last_updated": "2024-08-24T10:30:00.000Z"
}
```

### Docker Health Check

```bash
# Check container health
docker-compose ps

# View detailed logs
docker-compose logs -f price-tracker

# Monitor resource usage
docker stats price-tracker
```

## 🔍 Troubleshooting

### Common Issues

#### 1. Amazon_Flipkart Blocking Requests

**Symptoms**: Products not updating, scraping errors in logs

**Solutions**:
```bash
# Check logs for blocking indicators
docker-compose logs price-tracker | grep -i "blocked\|captcha\|403"

# Reduce request frequency (edit main.py)
schedule.every(2).hours.do(lambda: asyncio.create_task(check_all_prices(SessionLocal())))

# Use VPN or proxy if necessary
```

#### 2. Telegram Notifications Not Working

**Symptoms**: No alerts despite price drops

**Solutions**:
```bash
# Test bot token
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe"

# Test sending message
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage" \
  -d "chat_id=<YOUR_CHAT_ID>&text=Test message"

# Check environment variables
docker-compose exec price-tracker env | grep TELEGRAM
```

#### 3. Database Issues

**Symptoms**: Products not saving, database locked errors

**Solutions**:
```bash
# Check database file permissions
ls -la data/price_tracker.db

# Restart the application
docker-compose restart price-tracker

# Backup and recreate database if corrupted
docker-compose down
cp data/price_tracker.db data/backup.db
rm data/price_tracker.db
docker-compose up -d
```

#### 4. High Memory Usage

**Symptoms**: Container using excessive memory

**Solutions**:
```bash
# Monitor memory usage
docker stats price-tracker

# Add memory limit to docker-compose.yml
services:
  price-tracker:
    deploy:
      resources:
        limits:
          memory: 512M
```

### Debugging Tips

#### Enable Debug Logging

```python
# Add to main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🏠 Homelab Integration

### Portainer Stack

```yaml
version: '3.8'

services:
  price-tracker:
    image: your-registry/price-tracker:latest
    container_name: price-tracker
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /path/to/data:/app/data
      - /path/to/logs:/app/logs
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name price-tracker.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Backup Script

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/home/user/backups/price-tracker"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
docker-compose exec -T price-tracker cp /app/data/price_tracker.db /tmp/backup.db
docker cp $(docker-compose ps -q price-tracker):/tmp/backup.db "$BACKUP_DIR/price_tracker_$DATE.db"

# Keep only last 30 backups
find "$BACKUP_DIR" -name "price_tracker_*.db" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/price_tracker_$DATE.db"
```

## 🚀 Performance Optimization

### For 1000+ Products

#### 1. Database Optimization

```python
# Add to main.py for better performance
from sqlalchemy.pool import StaticPool

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 20
    },
    poolclass=StaticPool,
    pool_pre_ping=True
)
```

#### 2. Concurrent Processing

```python
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

async def check_prices_concurrent(products, max_workers=10):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, scraper.get_product_info, product.url)
            for product in products
        ]
        return await asyncio.gather(*tasks)
```

#### 3. Caching

```python
from functools import lru_cache
import time

@lru_cache(maxsize=1000)
def cached_product_info(url: str, timestamp: int):
    """Cache product info for 1 hour"""
    return scraper.get_product_info(url)

# Usage with hourly cache
def get_cached_info(url: str):
    current_hour = int(time.time()) // 3600
    return cached_product_info(url, current_hour)
```

## 📝 Contributing

### Development Setup

```bash
# Fork the repository and clone
git clone https://github.com/yourusername/Amazon_Flipkart-price-tracker.git
cd Amazon_Flipkart-price-tracker

# Create development environment
python -m venv dev-env
source dev-env/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest black flake8 mypy

# Run tests
pytest tests/

# Format code
black main.py
flake8 main.py
```

### Adding New Features

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `pytest`
6. Format code: `black .`
7. Create a pull request

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=main

# Run specific test
pytest tests/test_scraper.py -v
```

## 📄 License

MIT License

Copyright (c) 2024 Your Name

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## ⚠️ Legal Notice

This tool is for educational and personal use only. Please respect Amazon_Flipkart's robots.txt and terms of service. Users are responsible for ensuring their usage complies with applicable laws and website terms of service.


---

⭐ **Star this repository if you find it helpful!**

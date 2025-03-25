import logging
import os
import ssl
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.routes import router
from app.database import engine
from app.models import Base
from app.scheduler import start_scheduler
from app.utils import load_all_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable detailed SSL debugging
logging.getLogger('urllib3').setLevel(logging.DEBUG)
logging.getLogger('httpx').setLevel(logging.DEBUG)

# Log SSL/TLS info
logger = logging.getLogger(__name__)
logger.info(f"OpenSSL version: {ssl.OPENSSL_VERSION}")
logger.info(f"Default SSL context protocols: {ssl.PROTOCOL_TLS}")

# Check SSL connection to Meta APIs
def test_meta_api_connection():
    try:
        url = "https://graph.facebook.com/v22.0"
        logger.info(f"Testing connection to Meta API: {url}")
        response = requests.get(url, timeout=10)
        logger.info(f"Connection test status code: {response.status_code}")
        logger.info(f"Connection test headers: {response.headers}")
    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}")

# Create the database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Banquea WhatsApp Bot",
    description="Simple WhatsApp bot for medical questions",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    """Load data on startup"""
    load_all_data()

@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown event for the application.
    """
    logger.info("Shutting down the application")

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.getenv("PORT", 8000))
    
    # Log server startup details
    logger.info(f"Starting server on port {port}")
    
    # Get SSL configuration from environment
    ssl_keyfile = os.getenv("SSL_KEYFILE")
    ssl_certfile = os.getenv("SSL_CERTFILE")
    
    # If SSL files are provided, use them
    ssl_config = {}
    if ssl_keyfile and ssl_certfile:
        logger.info(f"Using SSL with cert: {ssl_certfile}, key: {ssl_keyfile}")
        ssl_config = {
            "ssl_keyfile": ssl_keyfile,
            "ssl_certfile": ssl_certfile,
        }
    else:
        logger.warning("Running without SSL. WhatsApp webhook verification requires HTTPS!")
    
    # Start the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        **ssl_config
    ) 
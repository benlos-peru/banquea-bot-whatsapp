import logging
import os
import ssl
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager

from app.routes import router
from app.database import engine
from app.models import Base
from app.scheduler import start_scheduler
from app.utils import load_all_data
from app.whatsapp import WhatsAppClient

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


# Create the database tables
Base.metadata.create_all(bind=engine)

# Test WhatsApp API connection (can be moved inside lifespan)
def test_meta_api_connection():
    try:
        logger.info("Testing connection to Meta APIs")
        client = WhatsAppClient()
        # Just validate that we have the necessary credentials
        if not client.phone_number_id or not client.access_token:
            logger.warning("WhatsApp API credentials are not properly configured")
        else:
            logger.info("WhatsApp API credentials found")
    except Exception as e:
        logger.error(f"Error connecting to Meta APIs: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup: Run before the application starts accepting requests
    try:
        logger.info("Starting up the application")
        
        # Test connection to Meta APIs
        test_meta_api_connection()
        
        # Load data on startup
        load_all_data()
        
        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
    
    yield  # This is where the application runs
    
    # Shutdown: Run when the application is shutting down
    try:
        logger.info("Shutting down the application")
        # Perform any cleanup tasks here if needed
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Banquea WhatsApp Bot",
    description="Simple WhatsApp bot for medical questions",
    version="1.0.0",
    lifespan=lifespan,
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

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.getenv("PORT", 8000))
    
    # Log server startup details
    logger.info(f"Starting server on port {port}")
    
    
    # Start the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    ) 

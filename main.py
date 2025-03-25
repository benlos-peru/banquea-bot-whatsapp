import logging
import os
import ssl
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

# Log SSL/TLS info
logger = logging.getLogger(__name__)
logger.info(f"OpenSSL version: {ssl.OPENSSL_VERSION}")

# Create the database tables
Base.metadata.create_all(bind=engine)

# Test WhatsApp API connection
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
        
        # Start the scheduler
        scheduler = start_scheduler()
        if scheduler:
            logger.info("Scheduler started successfully")
        else:
            logger.warning("Failed to start scheduler")
            
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
    description="WhatsApp bot for medical questions",
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

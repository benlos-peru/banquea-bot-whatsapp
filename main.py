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
    try:
        logger.info("Starting application and loading data...")
        load_all_data()
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")


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

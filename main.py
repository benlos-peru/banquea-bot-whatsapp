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
from app.utils import load_questions_from_csv
from app.database import SessionLocal

# Configure more verbose logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for more detailed logs
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Enable detailed SSL debugging
logging.getLogger('urllib3').setLevel(logging.DEBUG)
logging.getLogger('httpx').setLevel(logging.DEBUG)

# Log SSL/TLS info
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
    description="API for Banquea medical questions bot",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    """
    Startup event for the application.
    - Initialize database
    - Load questions from CSV files
    - Start the scheduler
    """
    try:
        logger.info("Starting up the application")
        
        # Test connection to Meta APIs
        test_meta_api_connection()
        
        # Create a database session
        db = SessionLocal()
        
        # Load questions from CSV files if they don't exist
        load_questions_from_csv(db)
        
        # Close the database session
        db.close()
        
        # Start the scheduler for sending questions
        scheduler = start_scheduler()
        if not scheduler:
            logger.error("Failed to start scheduler")
            
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")

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
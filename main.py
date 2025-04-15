from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
import logging
import os
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from src import models, database, routes, webhook
# Import scheduler functions
from src.scheduler import start_scheduler, shutdown_scheduler 
# Import SessionLocal for scheduler startup
from src.database import SessionLocal 

# Load environment variables
load_dotenv()

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging to file
log_level = 'DEBUG'
log_file = os.path.join('logs', 'whatsapp_bot.log')

# Configure root logger
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # File handler with rotation (10MB max size, keep 5 backup files)
        RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup: Run before the application starts accepting requests
    db = None # Initialize db to None
    try:
        logger.info("Starting WhatsApp bot application...")
        # Create database tables
        models.Base.metadata.create_all(bind=database.engine)
        logger.info("Database tables created successfully")
        
        # Get a DB session for starting the scheduler
        db = SessionLocal()
        # Start the scheduler and schedule initial jobs
        start_scheduler(db)
        logger.info("Scheduler started and initial jobs scheduled")
        
        yield # Application runs here
        
    finally:
        # Shutdown: Run when the application is shutting down
        logger.info("Shutting down WhatsApp bot application...")
        # Shutdown the scheduler
        shutdown_scheduler()
        logger.info("Scheduler shut down")
        # Close the DB session if it was opened
        if db:
            db.close()
            logger.info("Scheduler DB session closed")

# Create the FastAPI application
def create_app() -> FastAPI:
    app = FastAPI(
        title="WhatsApp Bot",
        description="A WhatsApp bot that sends periodic messages to users",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Include routers
    app.include_router(routes.router)
    app.include_router(webhook.router)
    
    @app.get("/")
    async def health_check():
        """Simple health check endpoint"""
        return {"status": "healthy"}
        
    return app

# Initialize the app at module level
server = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:server",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    )

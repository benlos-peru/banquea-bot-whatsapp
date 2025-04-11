from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
import logging
from src import models, database, routes, webhook

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup: Run before the application starts accepting requests
    try:
        logger.info("Starting WhatsApp bot application...")
        # Create database tables
        models.Base.metadata.create_all(bind=database.engine)
        logger.info("Database tables created successfully")
        yield
    finally:
        # Shutdown: Run when the application is shutting down
        logger.info("Shutting down WhatsApp bot application...")

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
app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    )

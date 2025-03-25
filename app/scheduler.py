from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
import logging

from .whatsapp import WhatsAppClient
from .database import SessionLocal

logger = logging.getLogger(__name__)

# Create WhatsApp client
whatsapp_client = WhatsAppClient()

async def scheduled_task():
    """
    Run the scheduled task to send questions to users.
    This function is called every hour by the scheduler.
    """
    try:
        # Create a new database session
        db = SessionLocal()
        
        # Send scheduled questions
        await send_scheduled_questions(db, whatsapp_client)
        
        # Close the database session
        db.close()
        
    except Exception as e:
        logger.error(f"Error in scheduled task: {str(e)}")

def start_scheduler():
    """
    Start the scheduler to send questions at the scheduled times.
    Should be called when starting the application.
    """
    try:
        scheduler = AsyncIOScheduler()
        
        # Schedule the task to run every hour
        # This allows us to check for users who should receive a message at each hour
        scheduler.add_job(
            scheduled_task,
            trigger=CronTrigger(hour="*", minute=0),  # Run at the start of every hour
            id="send_questions",
            name="Send scheduled questions to users",
            replace_existing=True,
        )
        
        scheduler.start()
        logger.info("Started scheduler for sending questions")
        
        return scheduler
        
    except Exception as e:
        logger.error(f"Error starting scheduler: {str(e)}")
        return None 
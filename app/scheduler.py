from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
import logging
from datetime import datetime, timedelta
import asyncio

from .whatsapp import WhatsAppClient
from .database import SessionLocal
from .utils import get_random_question
from . import crud

logger = logging.getLogger(__name__)

# Create WhatsApp client
whatsapp_client = WhatsAppClient()

# State machine for user conversation (must match routes.py)
STATES = {
    "INITIAL": 0,
    "AWAITING_CONFIRMATION": 1,
    "AWAITING_DAY": 2,
    "AWAITING_HOUR": 3,
    "SUBSCRIBED": 4,
    "AWAITING_QUESTION_RESPONSE": 5
}

async def send_scheduled_questions():
    """
    Send scheduled questions to users based on their preferred day and hour.
    This function is called every hour by the scheduler.
    """
    try:
        # Create a new database session
        db = SessionLocal()
        
        # Get the current day of week (0 = Monday, 6 = Sunday) and hour
        now = datetime.utcnow()
        current_day = now.weekday()  # Monday is 0, Sunday is 6
        current_hour = now.hour
        
        logger.info(f"Running scheduled task at day {current_day}, hour {current_hour}")
        
        # Find users who should receive a question at this time
        # They must be: active, not blacklisted, in SUBSCRIBED state, and have matching day/hour preferences
        users = db.query(crud.models.User).filter(
            crud.models.User.is_active == True,
            crud.models.User.is_blacklisted == False,
            crud.models.User.conversation_state == STATES["SUBSCRIBED"],
            crud.models.User.preferred_day == current_day,
            crud.models.User.preferred_hour == current_hour
        ).all()
        
        logger.info(f"Found {len(users)} users to send questions to")
        
        # Send a question to each eligible user
        for user in users:
            # Get a random question
            question = get_random_question()
            if not question:
                logger.error("No questions available")
                continue
                
            # Update user state
            user.conversation_state = STATES["AWAITING_QUESTION_RESPONSE"]
            user.last_question_id = question["id"]
            user.last_message_sent = datetime.utcnow()
            db.commit()
            
            # Send the question
            success = await whatsapp_client.send_question_list_message(
                user.phone_number,
                question["text"],
                question["options"],
                question["id"]
            )
            
            if success:
                logger.info(f"Successfully sent scheduled question to {user.phone_number}")
            else:
                logger.error(f"Failed to send scheduled question to {user.phone_number}")
                
            # Add a small delay between messages to avoid rate limiting
            await asyncio.sleep(1)
        
        # Close the database session
        db.close()
        
    except Exception as e:
        logger.error(f"Error in scheduled task: {str(e)}", exc_info=True)

def start_scheduler():
    """
    Start the scheduler to send questions at the scheduled times.
    Should be called when starting the application.
    """
    try:
        scheduler = AsyncIOScheduler()
        
        # Schedule the task to run every hour
        scheduler.add_job(
            send_scheduled_questions,
            trigger=CronTrigger(minute=0),  # Run at the start of every hour
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
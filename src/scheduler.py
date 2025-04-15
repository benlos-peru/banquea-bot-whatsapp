import logging
import random
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

# Import SessionLocal for creating sessions within jobs
from .database import SessionLocal 
from .models import User, UserState, UserQuestion
from .whatsapp import WhatsAppClient
from .questions import question_manager

logger = logging.getLogger(__name__)
whatsapp_client = WhatsAppClient()

# Setup timezone for Lima, Peru (UTC-5)
LIMA_TZ = pytz.timezone('America/Lima')

# Create job stores for persistent scheduling
jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///scheduler.sqlite')
}

# Create executors
executors = {
    'default': ThreadPoolExecutor(10)
}

# Create the scheduler
scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    timezone=LIMA_TZ
)

async def send_question_confirmation(user_id: int):
    """
    Send a confirmation template to ask if the user wants to receive a question now.
    Creates its own database session.
    
    Args:
        user_id: ID of the user to send confirmation to
    """
    logger.info(f"Job started: Sending question confirmation for user_id {user_id}")
    try:
        with SessionLocal() as db: # Create a new session for this job
            # Get the user
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"User with ID {user_id} not found in job")
                return
                
            # Check if user is still subscribed before sending
            if user.state != UserState.SUBSCRIBED:
                 logger.warning(f"User {user.phone_number} (ID: {user_id}) is no longer in SUBSCRIBED state ({user.state}). Skipping confirmation.")
                 # Optionally reschedule or clean up
                 # schedule_next_question(user, db) # Reschedule if needed, passing the new db session
                 return

            logger.info(f"Sending question confirmation to user {user.phone_number} (ID: {user_id})")
            
            # Update user state
            user.state = UserState.AWAITING_QUESTION_CONFIRMATION
            db.commit()
            
            # Send confirmation template
            await whatsapp_client.send_template_message(
                to_number=user.phone_number,
                template_name="confirmacion_pregunta"
            )
            logger.info(f"Successfully sent confirmation template to user {user.phone_number} (ID: {user_id})")

    except Exception as e:
        logger.error(f"Error in send_question_confirmation job for user_id {user_id}: {e}", exc_info=True)


async def send_random_question(user_id: int):
    """
    Send a random question to the user that they haven't answered before.
    Creates its own database session.
    
    Args:
        user_id: ID of the user to send question to
    """
    logger.info(f"Job started: Sending random question for user_id {user_id}")
    try:
        with SessionLocal() as db: # Create a new session for this job
            # Get the user
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"User with ID {user_id} not found in job")
                return
            
            # Get all previously sent question IDs for this user
            previous_questions = db.query(UserQuestion.question_id).filter(
                UserQuestion.user_id == user_id
            ).all()
            previous_question_ids = [q[0] for q in previous_questions]
            
            # Get a random question that the user hasn't seen
            all_questions = question_manager.questions_df
            
            if all_questions is None or all_questions.empty:
                logger.error("No questions available in the database")
                await whatsapp_client.send_text_message(
                    to_number=user.phone_number,
                    message_text="Lo siento, no hay preguntas disponibles en este momento."
                )
                return
            
            # If all questions have been answered, allow repeating
            available_questions = all_questions
            if previous_question_ids and len(previous_question_ids) < len(all_questions):
                available_questions = all_questions[~all_questions['question_id'].isin(previous_question_ids)]
            
            if available_questions.empty:
                logger.info(f"User {user.phone_number} has answered all questions, resetting")
                available_questions = all_questions
            
            # Get a random question
            question_row = available_questions.sample(n=1).iloc[0]
            question_id = question_row['question_id']
            question_text = question_row['question_text']
            
            # Get correct answer
            correct_answer = question_manager.correct_answers_df[
                question_manager.correct_answers_df['question_id'] == question_id
            ]['answer_text'].values[0]
            
            # Get incorrect answers
            incorrect_answers = []
            try:
                incorrect_answers = question_manager.incorrect_answers_df[
                    question_manager.incorrect_answers_df['question_id'] == question_id
                ]['answer_text'].tolist()
            except Exception as e:
                logger.warning(f"Could not retrieve incorrect answers: {str(e)}")
            
            # If not enough incorrect answers, generate some
            while len(incorrect_answers) < 3:
                # Get a random correct answer from another question
                random_answer = question_manager.correct_answers_df[
                    question_manager.correct_answers_df['question_id'] != question_id
                ].sample(n=1)['answer_text'].values[0]
                
                if random_answer not in incorrect_answers and random_answer != correct_answer:
                    incorrect_answers.append(random_answer)
            
            # Combine and shuffle all answers
            all_answers = [correct_answer] + incorrect_answers
            random.shuffle(all_answers)
            
            # Create section rows for the interactive list
            rows = []
            for i, answer in enumerate(all_answers):
                rows.append({
                    "id": f"answer_{i+1}",
                    "title": f"Opción {i+1}",
                    "description": answer  # Optional description can be empty
                })
            
            # Create the section for the interactive list
            section = {
                "title": "Selecciona tu respuesta",
                "rows": rows
            }
            
            # Record this question for the user
            user_question = UserQuestion(
                user_id=user_id,
                question_id=question_id,
                question_text=question_text,
                correct_answer=correct_answer,
                sent_at=datetime.now(LIMA_TZ),
                correct_answer_id=f"answer_{all_answers.index(correct_answer) + 1}"
            )
            db.add(user_question)
            
            # Update user state
            user.state = UserState.AWAITING_QUESTION_RESPONSE
            db.commit()
            
            logger.info(f"Sending question to user {user.phone_number} (ID: {user_id}): question_id={question_id}")
            
            # Send the question
            await whatsapp_client.send_interactive_list_message(
                to_number=user.phone_number,
                header_text="Pregunta Médica",
                body_text=question_text,
                footer_text="Selecciona la respuesta que consideres correcta.",
                button_text="Ver Opciones",
                sections=[section]
            )
            logger.info(f"Successfully sent question to user {user.phone_number} (ID: {user_id})")

    except Exception as e:
        logger.error(f"Error in send_random_question job for user_id {user_id}: {e}", exc_info=True)


def schedule_next_question(user: User, db: Session):
    """
    Schedule the next question confirmation for a user based on their preferences.
    Uses the provided session `db` to read user data for scheduling, 
    but the job itself (`send_question_confirmation`) will create its own session.
    
    Args:
        user: User model instance (read from the calling context's session)
        db: Database session (from the calling context, used only for reading user data)
    """
    # Ensure user object is up-to-date within the session if needed
    db.refresh(user) 
    
    if user.scheduled_day_of_week is None or user.scheduled_hour is None:
        logger.warning(f"User {user.phone_number} (ID: {user.id}) has no schedule set. Skipping scheduling.")
        return None

    # Calculate the next scheduled time
    now = datetime.now(LIMA_TZ)
    scheduled_day = user.scheduled_day_of_week
    scheduled_hour = user.scheduled_hour
    scheduled_minute = user.scheduled_minute # Get the minute
    
    # Calculate days until next scheduled day
    days_ahead = scheduled_day - now.weekday()
    if days_ahead < 0: # Target day already happened this week (e.g., today is Wed(2), target is Mon(0)) 
        days_ahead += 7
    elif days_ahead == 0: # Target day is today
        # Check if the time has already passed today
        current_time_in_lima = now.time()
        target_time = datetime.min.time().replace(hour=scheduled_hour, minute=scheduled_minute)
        if current_time_in_lima >= target_time:
            days_ahead += 7 # Schedule for next week if time already passed today
            
    # Create the scheduled datetime in the correct timezone
    next_date = now.date() + timedelta(days=days_ahead)
    # Combine date with scheduled hour and minute
    next_run_time_naive = datetime.combine(next_date, datetime.min.time().replace(hour=scheduled_hour, minute=scheduled_minute))
    next_run_time = LIMA_TZ.localize(next_run_time_naive)
    
    # This check might be redundant now due to the days_ahead logic, but keep for safety
    if next_run_time < now:
        logger.warning(f"Calculated next_run_time {next_run_time} is in the past compared to {now}. Adding 7 days.")
        next_run_time += timedelta(days=7)
    
    logger.info(f"Scheduling next question confirmation for user {user.phone_number} (ID: {user.id}) at {next_run_time}")
    
    # Schedule the job
    job_id = f"question_confirmation_{user.id}"
            
    # Add new job - Pass only the user_id, not the db session
    try:
        scheduler.add_job(
            send_question_confirmation, # The async function to call
            'date',
            run_date=next_run_time,
            id=job_id,
            args=[user.id], # Pass only the user ID
            replace_existing=True,
            misfire_grace_time=3600 # Allow job to run up to 1 hour late if scheduler was down
        )
        logger.info(f"Successfully scheduled job {job_id} for user {user.phone_number} at {next_run_time}")
    except Exception as e:
         logger.error(f"Failed to schedule job {job_id} for user {user.phone_number}: {e}", exc_info=True)

    
    return next_run_time

def schedule_all_users(db: Session):
    """
    Schedule questions for all subscribed users.
    
    Args:
        db: Database session
    """
    # Get all subscribed users
    users = db.query(User).filter(User.state == UserState.SUBSCRIBED).all()
    
    for user in users:
        try:
            schedule_next_question(user, db)
        except Exception as e:
            logger.error(f"Error scheduling user {user.phone_number}: {str(e)}")
    
    logger.info(f"Scheduled questions for {len(users)} users")

def start_scheduler(db: Session):
    """
    Start the scheduler and schedule all users.
    
    Args:
        db: Database session
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
        
        # Schedule all users
        schedule_all_users(db)
    else:
        logger.warning("Scheduler already running")

def shutdown_scheduler():
    """Shutdown the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down")
    else:
        logger.warning("Scheduler not running")

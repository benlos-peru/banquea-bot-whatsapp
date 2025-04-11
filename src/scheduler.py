import logging
import random
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

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

async def send_question_confirmation(user_id: int, db: Session):
    """
    Send a confirmation template to ask if the user wants to receive a question now.
    
    Args:
        user_id: ID of the user to send confirmation to
        db: Database session
    """
    # Get the user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"User with ID {user_id} not found")
        return
        
    logger.info(f"Sending question confirmation to user {user.phone_number}")
    
    # Update user state
    user.state = UserState.AWAITING_QUESTION_CONFIRMATION
    db.commit()
    
    # Send confirmation template
    await whatsapp_client.send_template_message(
        to_number=user.phone_number,
        template_name="confirmar_interaccion"
    )

async def send_random_question(user_id: int, db: Session):
    """
    Send a random question to the user that they haven't answered before.
    
    Args:
        user_id: ID of the user to send question to
        db: Database session
    """
    # Get the user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"User with ID {user_id} not found")
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
            "title": answer,
            "description": ""  # Optional description can be empty
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
    
    logger.info(f"Sending question to user {user.phone_number}: question_id={question_id}")
    
    # Send the question
    await whatsapp_client.send_interactive_list_message(
        to_number=user.phone_number,
        header_text="Pregunta Médica",
        body_text=question_text,
        footer_text="Selecciona la respuesta que consideres correcta.",
        button_text="Ver Opciones",
        sections=[section]
    )

def schedule_next_question(user: User, db: Session):
    """
    Schedule the next question for a user based on their preferences.
    
    Args:
        user: User model instance
        db: Database session
    """
    # Calculate the next scheduled time
    now = datetime.now(LIMA_TZ)
    scheduled_day = user.scheduled_day_of_week
    scheduled_hour = user.scheduled_hour
    
    # Calculate days until next scheduled day
    days_ahead = scheduled_day - now.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    
    # Create the scheduled datetime in the correct timezone
    next_date = now.date() + timedelta(days=days_ahead)
    next_run_time = LIMA_TZ.localize(
        datetime.combine(next_date, datetime.min.time()) + timedelta(hours=scheduled_hour)
    )
    
    # If the scheduled time is in the past, add a week
    if next_run_time < now:
        next_run_time += timedelta(days=7)
    
    logger.info(f"Scheduling next question for user {user.phone_number} at {next_run_time}")
    
    # Schedule the job
    job_id = f"question_confirmation_{user.id}"
    
    # Remove existing job if it exists
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    # Add new job
    scheduler.add_job(
        send_question_confirmation,
        'date',
        run_date=next_run_time,
        id=job_id,
        args=[user.id, db],
        replace_existing=True
    )
    
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

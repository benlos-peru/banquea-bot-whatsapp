import pandas as pd
import random
import os
import logging
from sqlalchemy.orm import Session
from typing import List, Dict, Tuple, Optional
import datetime

from .models import Question, QuestionOption, User, UserResponse
from .whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)

def load_questions_from_csv(db: Session):
    """
    Load questions and answers from CSV files.
    Should be called when initializing the application.
    """
    try:
        # Check if questions already exist in the database
        existing_count = db.query(Question).count()
        if existing_count > 0:
            logger.info(f"Database already contains {existing_count} questions. Skipping import.")
            return
        
        # Load the questions
        questions_file = os.path.join('preguntas', 'preguntas.csv')
        correct_answers_file = os.path.join('preguntas', 'respuestas_correctas.csv')
        incorrect_answers_file = os.path.join('preguntas', 'respuestas_incorrectas.csv')
        
        # Check if files exist
        if not all(os.path.exists(f) for f in [questions_file, correct_answers_file, incorrect_answers_file]):
            logger.error("Question files not found. Please check the paths.")
            return
        
        # Load questions
        questions_df = pd.read_csv(questions_file)
        correct_df = pd.read_csv(correct_answers_file)
        incorrect_df = pd.read_csv(incorrect_answers_file)
        
        # Process each question
        for _, row in questions_df.iterrows():
            question_id = row['id']
            question_text = row['pregunta']
            
            # Create the question
            db_question = Question(
                id=question_id,
                text=question_text,
                area=row.get('area', 'General')  # Default to 'General' if no area specified
            )
            db.add(db_question)
            
            # Get correct answers for this question
            correct_answers = correct_df[correct_df['idpregunta'] == question_id]['respuesta'].tolist()
            
            # Get incorrect answers for this question
            incorrect_answers = incorrect_df[incorrect_df['idpregunta'] == question_id]['respuesta'].tolist()
            
            # Add correct options
            for answer in correct_answers:
                db_option = QuestionOption(
                    question_id=question_id,
                    text=answer,
                    is_correct=True
                )
                db.add(db_option)
            
            # Add incorrect options
            for answer in incorrect_answers:
                db_option = QuestionOption(
                    question_id=question_id,
                    text=answer,
                    is_correct=False
                )
                db.add(db_option)
        
        # Commit changes
        db.commit()
        logger.info(f"Successfully imported {questions_df.shape[0]} questions")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error importing questions: {str(e)}")

def get_random_question(db: Session) -> Optional[Tuple[Question, List[QuestionOption]]]:
    """
    Get a random question with its options.
    
    Args:
        db: Database session
        
    Returns:
        Tuple of (Question, List[QuestionOption]) or None if no questions exist
    """
    try:
        # Get count of questions
        question_count = db.query(Question).count()
        if question_count == 0:
            return None
        
        # Get a random question
        random_id = random.randint(1, question_count)
        question = db.query(Question).filter(Question.id == random_id).first()
        
        # If not found, get any question
        if not question:
            question = db.query(Question).first()
        
        # Get options for this question
        options = db.query(QuestionOption).filter(QuestionOption.question_id == question.id).all()
        
        return question, options
    
    except Exception as e:
        logger.error(f"Error getting random question: {str(e)}")
        return None

def format_question_message(question: Question, options: List[QuestionOption]) -> str:
    """
    Format a question and its options as a WhatsApp message.
    
    Args:
        question: The question object
        options: List of option objects
        
    Returns:
        str: Formatted message
    """
    # Shuffle options
    random.shuffle(options)
    
    # Format message
    message = f"*PREGUNTA MÉDICA SEMANAL*\n\n{question.text}\n\n"
    
    for i, option in enumerate(options):
        message += f"{i+1}. {option.text}\n"
    
    message += "\nResponde con el número de la alternativa que consideres correcta."
    
    return message

async def send_scheduled_questions(db: Session, whatsapp_client: WhatsAppClient):
    """
    Send scheduled questions to users based on their preferred day and time.
    This function should be called by a scheduler every hour.
    """
    try:
        # Get current day of week (0-6, where 0 is Monday)
        current_day = datetime.datetime.now().weekday()
        # Get current hour (0-23)
        current_hour = datetime.datetime.now().hour
        
        # Find users who should receive a question now
        users = db.query(User).filter(
            User.is_active == True,
            User.is_blacklisted == False,
            User.preferred_day == current_day,
            User.preferred_hour == current_hour
        ).all()
        
        for user in users:
            # Check if it's been at least a week since the last message
            if user.last_message_sent:
                time_diff = datetime.datetime.utcnow() - user.last_message_sent
                if time_diff.days < 7:
                    continue
            
            # Get a random question
            question_data = get_random_question(db)
            if not question_data:
                logger.error("No questions available in the database")
                continue
                
            question, options = question_data
            
            # Format message
            message = format_question_message(question, options)
            
            # Send message
            success = await whatsapp_client.send_message(user.phone_number, message)
            
            if success:
                # Update last message sent time
                user.last_message_sent = datetime.datetime.utcnow()
                db.commit()
                logger.info(f"Successfully sent question to user {user.phone_number}")
            else:
                logger.error(f"Failed to send question to user {user.phone_number}")
    
    except Exception as e:
        logger.error(f"Error in send_scheduled_questions: {str(e)}")

def process_user_response(db: Session, user_id: int, response_text: str) -> Tuple[bool, str]:
    """
    Process a user's response to a question.
    
    Args:
        db: Database session
        user_id: The user's ID
        response_text: The user's response text
        
    Returns:
        Tuple of (is_correct: bool, feedback_message: str)
    """
    try:
        # Get the most recent question sent to this user
        last_message = db.query(User).filter(User.id == user_id).first().last_message_sent
        
        if not last_message:
            return False, "No tenemos registros de preguntas enviadas recientemente."
        
        # Try to parse the response as a number
        try:
            selected_option_num = int(response_text.strip())
        except ValueError:
            return False, "Por favor, responde con el número de la alternativa."
        
        # Get a random question for demonstration
        # In a real implementation, we would track which question was sent to the user
        question_data = get_random_question(db)
        if not question_data:
            return False, "Lo sentimos, ha ocurrido un error. Inténtalo de nuevo más tarde."
            
        question, options = question_data
        
        # Check if the selected option number is valid
        if selected_option_num < 1 or selected_option_num > len(options):
            return False, f"Por favor, selecciona un número entre 1 y {len(options)}."
        
        # Get the selected option
        selected_option = options[selected_option_num - 1]
        
        # Record the response
        user_response = UserResponse(
            user_id=user_id,
            question_id=question.id,
            selected_option_id=selected_option.id,
            is_correct=selected_option.is_correct
        )
        db.add(user_response)
        db.commit()
        
        # Get the correct answer
        correct_options = [opt for opt in options if opt.is_correct]
        correct_answer = correct_options[0].text if correct_options else "No hay respuesta correcta"
        
        # Prepare feedback message
        if selected_option.is_correct:
            feedback = f"¡Correcto! La respuesta es: {correct_answer}\n\nSeguirás recibiendo preguntas semanalmente."
        else:
            feedback = f"Incorrecto. La respuesta correcta es: {correct_answer}\n\nSeguirás recibiendo preguntas semanalmente."
        
        return selected_option.is_correct, feedback
        
    except Exception as e:
        logger.error(f"Error processing user response: {str(e)}")
        return False, "Lo sentimos, ha ocurrido un error. Inténtalo de nuevo más tarde." 
import pandas as pd
import random
import os
import logging
from sqlalchemy.orm import Session
from typing import List, Dict, Tuple, Optional, Any
import datetime

from .models import User, UserResponse
from .whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)

# Global in-memory questions store
questions_store = {}

def load_questions_from_csv():
    """
    Load questions and answers from CSV files into memory.
    Should be called when initializing the application.
    """
    global questions_store
    
    try:
        # Clear existing questions if any
        questions_store.clear()
        
        # Load the questions
        questions_file = os.path.join('preguntas', 'preguntas.csv')
        correct_answers_file = os.path.join('preguntas', 'respuestas_correctas.csv')
        incorrect_answers_file = os.path.join('preguntas', 'respuestas_incorrectas.csv')
        
        # Check if files exist
        for file_path in [questions_file, correct_answers_file, incorrect_answers_file]:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return
        
        # Load questions with duplicate column handling - only use the first occurrence of each column name
        questions_df = pd.read_csv(questions_file, low_memory=False, 
                                   dtype={'question_id': int})
        
        # Check for duplicate columns (specifically question_id)
        if list(questions_df.columns).count('question_id') > 1:
            logger.warning("Duplicate 'question_id' columns found in CSV. Using only the first occurrence.")
            
            # Get all column names
            all_cols = list(questions_df.columns)
            
            # Keep only the first occurrence of each column name
            unique_cols = []
            seen_cols = set()
            for col in all_cols:
                if col not in seen_cols:
                    unique_cols.append(col)
                    seen_cols.add(col)
            
            # Select only the unique columns
            questions_df = questions_df[unique_cols]
        
        # Load answers
        correct_answers_df = pd.read_csv(correct_answers_file, low_memory=False)
        incorrect_answers_df = pd.read_csv(incorrect_answers_file, low_memory=False)
        
        # Process each question
        for _, row in questions_df.iterrows():
            question_id = row['question_id']
            question_text = row['question_text']
            main_area = row.get('main_area', 'General')
            sub_area = row.get('sub_area', '')
            
            # Get correct answers for this question
            correct_options = correct_answers_df[correct_answers_df['question_id'] == question_id]['answer_text'].tolist()
            
            # Get incorrect answers for this question
            incorrect_options = incorrect_answers_df[incorrect_answers_df['question_id'] == question_id]['answer_text'].tolist()
            
            # Create options list
            options = []
            for text in correct_options:
                options.append({"text": text, "is_correct": True})
            
            for text in incorrect_options:
                options.append({"text": text, "is_correct": False})
            
            # Shuffle options
            random.shuffle(options)
            
            # Store question with its options
            questions_store[question_id] = {
                "id": question_id,
                "text": question_text,
                "area": main_area,
                "sub_area": sub_area,
                "options": options
            }
        
        logger.info(f"Successfully loaded {len(questions_store)} questions into memory")
        
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")
        # Add more detailed error information
        import traceback
        logger.error(traceback.format_exc())

def get_random_question() -> Optional[Dict[str, Any]]:
    """
    Get a random question with its options from the in-memory store.
    
    Returns:
        Dictionary containing question information or None if no questions exist
    """
    if not questions_store:
        return None
    
    # Get a random question
    question_id = random.choice(list(questions_store.keys()))
    return questions_store[question_id]

def format_question_message(question: Dict[str, Any]) -> str:
    """
    Format a question into a message string.
    
    Args:
        question: Question dictionary
        
    Returns:
        Formatted message string
    """
    options_text = []
    for i, option in enumerate(question["options"]):
        options_text.append(f"{i+1}) {option['text']}")
    
    formatted_message = (
        f"Pregunta: {question['text']}\n\n"
        f"{'\n'.join(options_text)}\n\n"
        f"Responde con el número de la alternativa correcta."
    )
    
    return formatted_message

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
            question_data = get_random_question()
            if not question_data:
                logger.error("No questions available in the database")
                continue
                
            question = question_data
            
            # Send question as interactive list
            success = await whatsapp_client.send_question_list_message(
                user.phone_number,
                question["text"],
                question["options"],
                question["id"]
            )
            
            if success:
                # Update last message sent time and question ID
                user.last_message_sent = datetime.datetime.utcnow()
                user.last_question_id = question["id"]
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
        question = get_random_question()
        if not question:
            return False, "Lo sentimos, ha ocurrido un error. Inténtalo de nuevo más tarde."
        
        options = question["options"]
        
        # Check if the selected option number is valid
        if selected_option_num < 1 or selected_option_num > len(options):
            return False, f"Por favor, selecciona un número entre 1 y {len(options)}."
        
        # Get the selected option
        selected_option = options[selected_option_num - 1]
        
        # Record the response (we'll need to modify this since we don't have option IDs anymore)
        user_response = UserResponse(
            user_id=user_id,
            question_id=question["id"],
            selected_option=selected_option_num,  # Store the option number instead
            is_correct=selected_option["is_correct"]
        )
        db.add(user_response)
        db.commit()
        
        # Get the correct answer
        correct_options = [opt["text"] for opt in options if opt["is_correct"]]
        correct_answer = correct_options[0] if correct_options else "No hay respuesta correcta"
        
        # Prepare feedback message
        if selected_option["is_correct"]:
            feedback = f"¡Correcto! La respuesta es: {correct_answer}\n\nSeguirás recibiendo preguntas semanalmente."
        else:
            feedback = f"Incorrecto. La respuesta correcta es: {correct_answer}\n\nSeguirás recibiendo preguntas semanalmente."
        
        return selected_option["is_correct"], feedback
        
    except Exception as e:
        logger.error(f"Error processing user response: {str(e)}")
        return False, "Lo sentimos, ha ocurrido un error. Inténtalo de nuevo más tarde."

def process_user_response_from_list(db: Session, user_id: int, question_id: int, option_num: int) -> Tuple[bool, str]:
    """
    Process a user's response to a question from an interactive list.
    
    Args:
        db: Database session
        user_id: The user's ID
        question_id: The question ID
        option_num: The selected option number (1-based)
        
    Returns:
        Tuple of (is_correct: bool, feedback_message: str)
    """
    try:
        # Get the user
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return False, "Usuario no encontrado."
        
        # Get the question from the store
        question = questions_store.get(question_id)
        
        if not question:
            return False, "No encontramos la pregunta correspondiente."
        
        options = question["options"]
        
        # Check if the selected option number is valid (option_num is 1-based)
        if option_num < 1 or option_num > len(options):
            return False, f"Opción inválida. Por favor, selecciona una opción entre 1 y {len(options)}."
        
        # Get the selected option (option_num is 1-based, array is 0-based)
        selected_option = options[option_num - 1]
        
        # Record the response
        user_response = UserResponse(
            user_id=user_id,
            question_id=question_id,
            selected_option=option_num,  # Store the option number
            is_correct=selected_option["is_correct"]
        )
        db.add(user_response)
        db.commit()
        
        # Get the correct answer(s)
        correct_options = [opt["text"] for opt in options if opt["is_correct"]]
        correct_answer = correct_options[0] if correct_options else "No hay respuesta correcta"
        
        # Prepare feedback message
        if selected_option["is_correct"]:
            feedback = f"¡Correcto! La respuesta es: {correct_answer}"
        else:
            feedback = f"Incorrecto. La respuesta correcta es: {correct_answer}"
        
        return selected_option["is_correct"], feedback
        
    except Exception as e:
        logger.error(f"Error processing user response: {str(e)}")
        return False, "Lo sentimos, ha ocurrido un error. Inténtalo de nuevo más tarde." 
import pandas as pd
import random
import os
import logging
import datetime
from typing import Dict, List, Tuple, Optional, Any
import json

logger = logging.getLogger(__name__)

# Global stores
questions_store = {}
users_store = {}
responses_store = []

def load_all_data():
    """Load all data from CSV files"""
    load_questions()
    load_users()
    load_responses()

def load_questions():
    """Load questions from CSV files"""
    global questions_store
    
    try:
        questions_file = os.path.join('preguntas', 'preguntas.csv')
        correct_answers_file = os.path.join('preguntas', 'respuestas_correctas.csv')
        incorrect_answers_file = os.path.join('preguntas', 'respuestas_incorrectas.csv')
        
        # Load questions - only use needed columns
        questions_df = pd.read_csv(questions_file, usecols=[0, 2])  # question_id, question_text
        correct_df = pd.read_csv(correct_answers_file)
        incorrect_df = pd.read_csv(incorrect_answers_file)
        
        for _, row in questions_df.iterrows():
            qid = int(row['question_id'])
            
            # Get answers
            correct = correct_df[correct_df['pregunta_id'] == qid]['respuesta_texto'].tolist()
            incorrect = incorrect_df[incorrect_df['pregunta_id'] == qid]['respuesta_texto'].tolist()
            
            # Create options
            options = (
                [{"text": str(text), "is_correct": True} for text in correct if pd.notna(text)] +
                [{"text": str(text), "is_correct": False} for text in incorrect if pd.notna(text)]
            )
            
            if options:  # Only store questions with answers
                random.shuffle(options)
                questions_store[qid] = {
                    "id": qid,
                    "text": row['question_text'],
                    "options": options
                }
        
        logger.info(f"Loaded {len(questions_store)} questions")
        
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")

def save_users():
    """Save users to CSV"""
    users_file = 'data/users.csv'
    os.makedirs('data', exist_ok=True)
    
    df = pd.DataFrame(users_store.values())
    df.to_csv(users_file, index=False)

def load_users():
    """Load users from CSV"""
    global users_store
    users_file = 'data/users.csv'
    
    if os.path.exists(users_file):
        df = pd.read_csv(users_file)
        users_store = {row['phone_number']: row.to_dict() for _, row in df.iterrows()}

def save_response(phone_number: str, question_id: int, selected_option: int, is_correct: bool):
    """Save a user response"""
    responses_store.append({
        'phone_number': phone_number,
        'question_id': question_id,
        'selected_option': selected_option,
        'is_correct': is_correct,
        'timestamp': datetime.datetime.now().isoformat()
    })
    
    # Save to CSV
    df = pd.DataFrame(responses_store)
    os.makedirs('data', exist_ok=True)
    df.to_csv('data/responses.csv', index=False)

def load_responses():
    """Load responses from CSV"""
    global responses_store
    responses_file = 'data/responses.csv'
    
    if os.path.exists(responses_file):
        df = pd.read_csv(responses_file)
        responses_store = df.to_dict('records')

def get_random_question() -> Optional[Dict]:
    """Get a random question"""
    if not questions_store:
        return None
    return random.choice(list(questions_store.values()))

def process_user_response(phone_number: str, question_id: int, option_num: int) -> Tuple[bool, str]:
    """Process a user's response to a question"""
    try:
        question = questions_store.get(question_id)
        if not question or option_num < 1 or option_num > len(question['options']):
            return False, "Respuesta inválida"
        
        selected = question['options'][option_num - 1]
        is_correct = selected['is_correct']
        
        # Save response
        save_response(phone_number, question_id, option_num, is_correct)
        
        # Get correct answer for feedback
        correct_answer = next(opt['text'] for opt in question['options'] if opt['is_correct'])
        
        if is_correct:
            feedback = f"¡Correcto! La respuesta es: {correct_answer}"
        else:
            feedback = f"Incorrecto. La respuesta correcta es: {correct_answer}"
            
        return is_correct, f"{feedback}\n\nRecibirás otra pregunta la próxima semana."
        
    except Exception as e:
        logger.error(f"Error processing response: {str(e)}")
        return False, "Error procesando tu respuesta"

def add_or_update_user(phone_number: str, name: str = None):
    """Add or update a user"""
    users_store[phone_number] = {
        'phone_number': phone_number,
        'name': name,
        'created_at': datetime.datetime.now().isoformat(),
        'last_message': datetime.datetime.now().isoformat()
    }
    save_users() 
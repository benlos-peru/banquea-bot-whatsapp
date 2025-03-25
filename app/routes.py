from fastapi import APIRouter, Depends, HTTPException, Form, Body, BackgroundTasks, Request, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
import logging

import time
import json
import functools
from datetime import datetime


from . import crud, schemas, models
from .database import get_db
from .whatsapp import WhatsAppClient
from .utils import (
    process_user_response, get_random_question, 
    add_or_update_user, questions_store, users_store, load_questions, load_users, load_responses, load_all_data,
    questions_store, users_store
)

router = APIRouter()
whatsapp_client = WhatsAppClient()
logger = logging.getLogger(__name__)

# State machine for user conversation
STATES = {
    "INITIAL": 0,
    "AWAITING_CONFIRMATION": 1,
    "AWAITING_DAY": 2,
    "AWAITING_HOUR": 3,
    "SUBSCRIBED": 4,
    "AWAITING_QUESTION_RESPONSE": 5
}

user_states = {}  # In-memory state storage. In production, use a database or Redis

# Create a decorator to log execution time
def log_execution_time(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = f"req_{int(time.time())}"
        start_time = time.time()
        
        # Log start of execution
        logger.info(f"[{request_id}] Starting execution of {func.__name__} at {datetime.now().isoformat()}")
        
        try:
            # Pass request_id to the function if it accepts it
            if 'request_id' in func.__code__.co_varnames:
                kwargs['request_id'] = request_id
                result = await func(*args, **kwargs)
            else:
                result = await func(*args, **kwargs)
            
            # Log successful completion
            end_time = time.time()
            execution_time = end_time - start_time
            logger.info(f"[{request_id}] Successfully completed {func.__name__} in {execution_time:.3f}s")
            
            # Add request_id to result if it's a dict
            if isinstance(result, dict):
                result['request_id'] = request_id
                
            return result
            
        except Exception as e:
            # Log error
            end_time = time.time()
            execution_time = end_time - start_time
            logger.error(f"[{request_id}] Error in {func.__name__} after {execution_time:.3f}s: {str(e)}", exc_info=True)
            raise
            
    return wrapper

def get_user_state(phone_number: str) -> Dict[str, Any]:
    """Get or initialize user state"""
    if phone_number not in user_states:
        user_states[phone_number] = {
            "state": STATES["INITIAL"],
            "temp_data": {}
        }
    return user_states[phone_number]

def set_user_state(phone_number: str, state: int, temp_data: Optional[Dict[str, Any]] = None):
    """Update user state"""
    user_states[phone_number] = {
        "state": state,
        "temp_data": temp_data or {}
    }

@router.get("/")
def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "questions_loaded": len(questions_store)}

@router.get("/debug/user-state/{phone_number}")
def get_user_state_endpoint(phone_number: str):
    """Debug endpoint to check a user's state"""
    state = get_user_state(phone_number)
    return {
        "phone_number": phone_number,
        "state": state.get("state"),
        "state_name": next((k for k, v in STATES.items() if v == state.get("state")), "UNKNOWN"),
        "temp_data": state.get("temp_data", {})
    }

@router.get("/webhook")
async def verify_webhook(request: Request):
    """Verify webhook for WhatsApp API"""
    try:
        query_params = dict(request.query_params)
        mode = query_params.get("hub.mode")
        token = query_params.get("hub.verify_token")
        challenge = query_params.get("hub.challenge")
        
        if mode == "subscribe" and token == whatsapp_client.verify_token:
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification failed")
    except Exception as e:
        logger.error(f"Error verifying webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def webhook(request: Request):
    """Handle WhatsApp webhook"""
    try:
        body = await request.json()
        logger.info(f"Received webhook: {json.dumps(body)}")
        
        # Check if this is just a WhatsApp verification message
        if "object" not in body or body.get("object") != "whatsapp_business_account":
            return {"status": "ignored"}
            
        # Process messages
        try:
            entry = body["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            
            # Check if there are messages
            if "messages" not in value:
                return {"status": "no messages"}
                
            message = value["messages"][0]
            phone_number = message["from"]
            
            # Get contact info if available
            name = None
            if "contacts" in value and value["contacts"]:
                contact = value["contacts"][0]
                if "profile" in contact:
                    name = contact["profile"].get("name")
            
            # Add or update user
            add_or_update_user(phone_number, name)
            
            # Process different message types
            if message["type"] == "interactive" and "list_reply" in message["interactive"]:
                # Handle interactive list reply (answer to a question)
                list_reply = message["interactive"]["list_reply"]
                option_id = list_reply["id"]  # Format: q_{question_id}_opt_{option_number}
                
                # Parse question_id and option_number
                parts = option_id.split("_")
                if len(parts) >= 4:
                    question_id = int(parts[1])
                    option_num = int(parts[3])
                    
                    # Process response
                    is_correct, feedback = process_user_response(phone_number, question_id, option_num)
                    
                    # Send feedback
                    await whatsapp_client.send_message(phone_number, feedback)
                else:
                    logger.error(f"Invalid option ID format: {option_id}")
                    await whatsapp_client.send_message(phone_number, "Lo siento, hubo un error procesando tu respuesta.")
            
            elif message["type"] == "text":
                # Handle text message - send a random question
                text = message["text"]["body"].strip().lower()
                
                if text in ["hola", "hello", "hi", "inicio", "start", "comenzar"]:
                    # Welcome message
                    await whatsapp_client.send_message(
                        phone_number, 
                        "¡Hola! Soy el bot de Banquea que te enviará preguntas médicas. Responde para recibir tu primera pregunta."
                    )
                    
                # Send a random question
                question = get_random_question()
                if question:
                    await whatsapp_client.send_question_list_message(
                        phone_number,
                        question["text"],
                        question["options"],
                        question["id"]
                    )
                else:
                    await whatsapp_client.send_message(
                    phone_number,
                        "Lo siento, no hay preguntas disponibles en este momento."
                    )
            
            return {"status": "success"}
            
        except KeyError as e:
            logger.error(f"KeyError processing webhook: {str(e)}")
            return {"status": "error", "error": f"Missing field: {str(e)}"}
    
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("/admin/blacklist/{phone_number}")
def blacklist_user_endpoint(
    phone_number: str,
    db: Session = Depends(get_db)
):
    """Admin endpoint to blacklist a user"""
    user = crud.get_user_by_phone(db, phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    crud.blacklist_user(db, user.id)
    return {"status": "success", "message": f"User {phone_number} has been blacklisted"}

@router.post("/admin/load-questions")
def reload_questions():
    """Admin endpoint to reload questions from CSV files"""
    try:
        load_questions()
        return {"status": "success", "message": f"Successfully loaded {len(questions_store)} questions"}
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading questions: {str(e)}")

@router.post("/admin/reload-all-data")
def reload_all_data():
    """Admin endpoint to reload all data from CSV files"""
    try:
        load_all_data()
        return {
            "status": "success", 
            "questions": len(questions_store),
            "users": len(users_store)
        }
    except Exception as e:
        logger.error(f"Error reloading data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/stats")
def get_stats():
    """Get statistics about the data"""
    return {
        "questions": len(questions_store),
        "users": len(users_store)
    }

@router.post("/admin/add-test-user")
async def add_test_user(
    phone_number: str = Body(...),
    template_name: str = Body(...),
    language_code: str = Body("es"),
    db: Session = Depends(get_db)
):
    """
    Add a test user and send a template message to them.
    This is useful for testing the WhatsApp integration.
    
    Args:
        phone_number: The user's phone number with country code (e.g., +51973296571)
        template_name: The name of the template to send
        language_code: The language code for the template (default: es)
    """
    try:
        # Clean up phone number
        if not phone_number.startswith("+"):
            phone_number = f"+{phone_number}"
        
        # Create or get user
        user = crud.get_user_by_phone(db, phone_number)
        if not user:
            user = crud.create_user(db, phone_number)
            logger.info(f"Created new test user with phone number: {phone_number}")
        else:
            logger.info(f"Using existing user with phone number: {phone_number}")
        
        # Send template message
        success = await whatsapp_client.send_template_message(
            phone_number,
            template_name,
            language_code
        )
        
        if success:
            return {
                "status": "success",
                "message": f"Template message '{template_name}' sent successfully to {phone_number}",
                "user_id": user.id
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to send template message to {phone_number}"
            }
            
    except Exception as e:
        logger.error(f"Error adding test user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding test user: {str(e)}")

@router.post("/admin/send-day-selection")
async def send_day_selection_test(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Send a day selection list to a test user.
    
    Args:
        request: FastAPI request object
        db: Database session
    """
    try:
        # Get JSON from request body
        body = await request.json()
        phone_number = body.get("phone_number")
        
        if not phone_number:
            raise HTTPException(status_code=400, detail="phone_number is required")
        
        # Clean up phone number
        if not phone_number.startswith("+"):
            phone_number = f"+{phone_number}"
        
        # Create or get user
        user = crud.get_user_by_phone(db, phone_number)
        if not user:
            user = crud.create_user(db, phone_number)
            logger.info(f"Created new test user with phone number: {phone_number}")
        else:
            logger.info(f"Using existing user with phone number: {phone_number}")
        
        # Send day selection message
        await send_day_selection_message(
            phone_number,
            "Por favor selecciona el día de la semana en que deseas recibir las preguntas:"
        )
        
        return {
            "status": "success",
            "message": f"Day selection message sent successfully to {phone_number}",
            "user_id": user.id
        }
            
    except Exception as e:
        logger.error(f"Error sending day selection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending day selection: {str(e)}")

@router.post("/admin/send-button-message")
async def send_button_message_test(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Send a button message to a test user.
    
    Args:
        request: FastAPI request object
        db: Database session
    """
    try:
        # Get JSON from request body
        body = await request.json()
        phone_number = body.get("phone_number")
        
        if not phone_number:
            raise HTTPException(status_code=400, detail="phone_number is required")
        
        # Clean up phone number
        if not phone_number.startswith("+"):
            phone_number = f"+{phone_number}"
        
        # Create or get user
        user = crud.get_user_by_phone(db, phone_number)
        if not user:
            user = crud.create_user(db, phone_number)
            logger.info(f"Created new test user with phone number: {phone_number}")
        else:
            logger.info(f"Using existing user with phone number: {phone_number}")
        
        # Send button message
        await send_simple_button_message(
            phone_number,
            "¿Estás listo para comenzar con las preguntas médicas?",
            "Configuración de preguntas"
        )
        
        return {
            "status": "success",
            "message": f"Button message sent successfully to {phone_number}",
            "user_id": user.id
        }
            
    except Exception as e:
        logger.error(f"Error sending button message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending button message: {str(e)}")

@log_execution_time
async def send_simple_button_message(phone_number: str, body_text: str, header_text: Optional[str] = None, request_id: str = None):
    """
    Send a simple button message with Yes/No options
    
    Args:
        phone_number: The user's phone number
        body_text: The main message text
        header_text: Optional header text
        request_id: Request ID for consistent logging
    """
    logger.info(f"[{request_id}] Preparing button message for {phone_number}")
    
    # Create the buttons
    buttons = [
        {
            "type": "reply",
            "reply": {
                "id": "yes_button",
                "title": "Sí"
            }
        },
        {
            "type": "reply",
            "reply": {
                "id": "no_button",
                "title": "No"
            }
        }
    ]
    
    logger.info(f"[{request_id}] Sending button message with {len(buttons)} options")
    
    # Send the button message
    result = await whatsapp_client.send_button_message(
        to_number=phone_number,
        body_text=body_text,
        buttons=buttons,
        header_text=header_text,
        footer_text="Banquea - Bot de preguntas médicas"
    )
    
    logger.info(f"[{request_id}] Button message send result: {result}")
    return result 

async def handle_day_selection(phone_number: str, day_id: str, day_title: str, user_id: int, db: Session, request_id: str = None):
    """
    Handle day selection and go directly to sending a question.
    
    Args:
        phone_number: The user's phone number
        day_id: The selected day ID
        day_title: The selected day title
        user_id: The user's ID
        db: Database session
        request_id: Request ID for consistent logging
    """
    try:
        # Convert day name to day index (0 = Monday, 6 = Sunday)
        day_map = {
            "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, 
            "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
        }
        
        day_value = day_map.get(day_title.lower())
        
        if day_value is None:
            logger.error(f"[{request_id}] Invalid day selected: {day_title}")
            await whatsapp_client.send_message(
                phone_number,
                "Lo siento, hubo un error con tu selección. Por favor intenta de nuevo."
            )
            return False
            
        # Update user preferences (set default hour to 9)
        crud.update_user_preferences(db, user_id, day_value, 9)  # Default to 9 AM
        logger.info(f"[{request_id}] Updated user preferences: day={day_value}, hour=9 (default)")
        
        # Get a random question
        question = get_random_question()
        if not question:
            logger.error(f"[{request_id}] No questions available")
            await whatsapp_client.send_message(
                phone_number,
                "Lo sentimos, no pudimos encontrar preguntas disponibles. Por favor intenta más tarde."
            )
            return False
        
        # Store the current question ID for the user
        user = crud.get_user_by_id(db, user_id)
        user.last_question_id = question["id"]
        user.last_message_sent = datetime.utcnow()
        db.commit()
        
        # Send the question as an interactive list
        result = await whatsapp_client.send_question_list_message(
            phone_number,
            question["text"],
            question["options"],
            question["id"]
        )
        
        if result:
            # Set user state to waiting for question response
            set_user_state(phone_number, STATES["AWAITING_QUESTION_RESPONSE"])
            logger.info(f"[{request_id}] Set user state to AWAITING_QUESTION_RESPONSE")
            return True
        else:
            logger.error(f"[{request_id}] Failed to send question to {phone_number}")
            return False
            
    except Exception as e:
        logger.error(f"[{request_id}] Error handling day selection: {str(e)}")
        return False

@router.post("/admin/send-question-to-all")
async def send_question_to_all():
    """Send a random question to all users"""
    try:
        question = get_random_question()
        if not question:
            raise HTTPException(status_code=400, detail="No questions available")
        
        success = 0
        failed = 0
        
        for phone_number in users_store:
            result = await whatsapp_client.send_question_list_message(
                phone_number,
                question["text"],
                question["options"],
                question["id"]
            )
            
            if result:
                success += 1
            else:
                failed += 1
        
        return {
            "status": "success",
            "sent": success,
            "failed": failed
        }
        
    except Exception as e:
        logger.error(f"Error sending questions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 
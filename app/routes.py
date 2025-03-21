from fastapi import APIRouter, Depends, HTTPException, Form, Body, BackgroundTasks, Request, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
import logging
import re
import httpx
import time
import json
import functools
from datetime import datetime
import uuid

from . import crud, schemas, models
from .database import get_db
from .whatsapp import WhatsAppClient
from .utils import load_questions_from_csv, process_user_response

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
def read_root():
    """Root endpoint for health check"""
    return {"status": "ok", "message": "Banquea WhatsApp Bot API is running"}

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
async def verify_webhook(
    request: Request,
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge")
):
    """
    Handle the webhook verification request from WhatsApp Cloud API.
    This is required when setting up the webhook in the Meta Developer Portal.
    """
    # Log full request details
    logger.info(f"Webhook verification request received")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Query params - hub.mode: {hub_mode}, hub.verify_token: {hub_verify_token}, hub.challenge: {hub_challenge}")
    
    # Verify the webhook
    challenge = whatsapp_client.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    
    if challenge:
        logger.info(f"Webhook verification successful, returning challenge: {challenge}")
        return int(challenge)
    
    logger.error(f"Webhook verification failed - Incorrect verification token")
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/webhook")
@log_execution_time
async def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    request_id: str = None
):
    """
    Webhook for WhatsApp messages.
    """
    if not request_id:
        request_id = str(uuid.uuid4())
    
    # Log detailed request information
    logger.info(f"[{request_id}] Webhook request received - Method: {request.method}, Path: {request.url.path}")
    logger.info(f"[{request_id}] Request headers: {dict(request.headers)}")
    
    try:
        # Get raw request body first for debugging
        raw_body = await request.body()
        logger.info(f"[{request_id}] Raw request body: {raw_body}")
        
        # Parse as JSON for normal processing
        payload = await request.json()
        logger.info(f"[{request_id}] Received webhook payload: {json.dumps(payload)}")
        
        # Process the webhook payload
        message_data = whatsapp_client.process_webhook_payload(payload)
        
        if not message_data:
            # Not a valid message event or no messages in the payload
            logger.warning(f"[{request_id}] No processable messages in payload")
            return {"status": "success", "message": "No processable messages"}
        
        # Extract data from the message
        phone_number = message_data.get("from_number", "")
        message_body = message_data.get("body", "")
        message_type = message_data.get("message_type", "")
        message_id = message_data.get("message_id", "")
        interactive_data = message_data.get("interactive_data", {})
        
        if not phone_number:
            logger.warning(f"[{request_id}] Incomplete message data: missing phone number")
            return {"status": "success", "message": "Incomplete message data"}
        
        # Enhanced logging for debugging
        logger.info(f"[{request_id}] Processing message - From: {phone_number}, ID: {message_id}, Type: {message_type}, Content: {message_body}")
        if interactive_data:
            logger.info(f"[{request_id}] Interactive data: {json.dumps(interactive_data)}")

        # Get or create user
        user = crud.get_user_by_phone(db, phone_number)
        if not user:
            user = crud.create_user(db, phone_number)
            logger.info(f"[{request_id}] Created new user with phone number: {phone_number}, ID: {user.id}")
        else:
            logger.info(f"[{request_id}] Existing user found - Phone: {phone_number}, ID: {user.id}, Active: {user.is_active}")

        # Get user state
        user_state = get_user_state(phone_number)
        current_state = user_state["state"]
        state_name = next((k for k, v in STATES.items() if v == current_state), "UNKNOWN")
        logger.info(f"[{request_id}] Current user state: {state_name} ({current_state}), Temp data: {user_state.get('temp_data', {})}")
        
        # Process message based on state
        response_message = ""
        
        # Handle interactive messages
        if message_type == "interactive" and interactive_data:
            logger.info(f"[{request_id}] Processing interactive message for state {state_name}")
            
            # Get the reply type
            reply_type = interactive_data.get("reply_type", "")
            button_id = interactive_data.get("id", "")
            title = interactive_data.get("title", "")
            
            logger.info(f"[{request_id}] Interactive details - Type: {reply_type}, ID: {button_id}, Title: {title}")
            
            # Handle button replies
            if reply_type == "button_reply":
                if button_id == "yes_button":
                    # User clicked "Yes" button, send day selection
                    logger.info(f"[{request_id}] User clicked Yes button, sending day selection")
                    await send_day_selection_message(
                        phone_number, 
                        "Por favor selecciona el día de la semana en que deseas recibir las preguntas:"
                    )
                    set_user_state(phone_number, STATES["AWAITING_DAY"])
                    # Log state transition
                    logger.info(f"[{request_id}] State transition: {state_name} -> AWAITING_DAY")
                    return {"status": "success"}
                elif button_id == "no_button":
                    # User clicked "No" button
                    response_message = "Entendido. Si cambias de opinión, escribe INICIAR en cualquier momento."
                    crud.deactivate_user(db, user.id)
                    set_user_state(phone_number, STATES["INITIAL"])
                    # Log state transition and user deactivation
                    logger.info(f"[{request_id}] User deactivated - ID: {user.id}")
                    logger.info(f"[{request_id}] State transition: {state_name} -> INITIAL")
            
            # Handle list selection replies
            elif reply_type == "list_reply" and current_state == STATES["AWAITING_DAY"]:
                # User selected a day from a list
                day_id = button_id
                day_title = title
                
                logger.info(f"[{request_id}] User selected day: {day_title} (ID: {day_id})")
                
                # Convert day name to day index (0 = Monday, 6 = Sunday)
                day_map = {
                    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, 
                    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
                }
                
                day_value = day_map.get(day_title.lower())
                
                if day_value is not None:
                    # Store the selected day
                    temp_data = user_state["temp_data"]
                    temp_data["preferred_day"] = day_value
                    
                    # Ask for the hour
                    response_message = (
                        f"Has seleccionado {day_title}. "
                        "¿A qué hora prefieres recibir las preguntas? "
                        "Responde con un número del 0 al 23 (formato 24 horas)."
                    )
                    set_user_state(phone_number, STATES["AWAITING_HOUR"], temp_data)
                    logger.info(f"[{request_id}] Updated user state to AWAITING_HOUR with day value {day_value}")
                    logger.info(f"[{request_id}] State transition: {state_name} -> AWAITING_HOUR")
                else:
                    response_message = "No pude reconocer el día seleccionado. Por favor, selecciona un día de la semana."
                    logger.warning(f"[{request_id}] Could not recognize day value from title: {day_title}")
                
                # Send response
                if response_message:
                    logger.info(f"[{request_id}] Sending response: {response_message}")
                    send_result = await whatsapp_client.send_message(phone_number, response_message)
                    logger.info(f"[{request_id}] Message send result: {send_result}")
                
                return {"status": "success"}
        
        # Normal text message processing
        if current_state == STATES["INITIAL"]:
            # First contact with the user or user in initial state
            # Send button message instead of just text
            logger.info(f"[{request_id}] Sending welcome message with buttons")
            send_result = await send_simple_button_message(
                phone_number,
                "Bienvenido/a al bot de preguntas médicas de Banquea. Este bot te enviará preguntas semanales para reforzar tus conocimientos médicos. ¿Deseas recibir preguntas semanales?",
                "Configuración de suscripción"
            )
            logger.info(f"[{request_id}] Button message send result: {send_result}")
            
            set_user_state(phone_number, STATES["AWAITING_CONFIRMATION"])
            logger.info(f"[{request_id}] State transition: {state_name} -> AWAITING_CONFIRMATION")
            
            return {"status": "success"}
            
        elif current_state == STATES["AWAITING_CONFIRMATION"]:
            # User responding to confirmation
            if message_body.lower() in ["si", "sí", "yes", "y"]:
                # Create a list message for day selection
                logger.info(f"[{request_id}] User confirmed subscription, sending day selection message")
                await send_day_selection_message(
                    phone_number, 
                    "Por favor selecciona el día de la semana en que deseas recibir las preguntas:"
                )
                set_user_state(phone_number, STATES["AWAITING_DAY"])
                logger.info(f"[{request_id}] State transition: {state_name} -> AWAITING_DAY")
                
                return {"status": "success"}
            elif message_body.lower() in ["no", "n"]:
                response_message = "Entendido. No recibirás preguntas semanales. Si cambias de opinión, escribe INICIAR."
                crud.deactivate_user(db, user.id)
                set_user_state(phone_number, STATES["INITIAL"])
                logger.info(f"[{request_id}] User declined subscription and was deactivated")
                logger.info(f"[{request_id}] State transition: {state_name} -> INITIAL")
            else:
                response_message = "No entendí tu respuesta. Por favor responde SI o NO, o usa los botones enviados."
                logger.info(f"[{request_id}] User provided unrecognized confirmation response: {message_body}")
                
        elif current_state == STATES["AWAITING_DAY"]:
            # If we get here, it means the user responded with text instead of using the list
            try:
                day = int(message_body.strip())
                if 1 <= day <= 7:
                    # Convert to 0-6 format where 0 is Monday
                    day_value = day - 1
                    
                    # Store temporarily
                    temp_data = user_state["temp_data"]
                    temp_data["preferred_day"] = day_value
                    
                    response_message = (
                        f"Has seleccionado el día {day}. "
                        "¿A qué hora prefieres recibir las preguntas? "
                        "Responde con un número del 0 al 23 (formato 24 horas)."
                    )
                    set_user_state(phone_number, STATES["AWAITING_HOUR"], temp_data)
                    logger.info(f"[{request_id}] Updated user state to AWAITING_HOUR with day value {day_value}")
                else:
                    response_message = "Por favor, elige un número del 1 al 7, donde 1 es lunes y 7 es domingo."
            except ValueError:
                # Not a number, let's try to interpret the day name
                day_map = {
                    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, 
                    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
                }
                
                day_value = day_map.get(message_body.lower())
                
                if day_value is not None:
                    # Store the day value
                    temp_data = user_state["temp_data"]
                    temp_data["preferred_day"] = day_value
                    
                    response_message = (
                        f"Has seleccionado {message_body}. "
                        "¿A qué hora prefieres recibir las preguntas? "
                        "Responde con un número del 0 al 23 (formato 24 horas)."
                    )
                    set_user_state(phone_number, STATES["AWAITING_HOUR"], temp_data)
                    logger.info(f"[{request_id}] Updated user state to AWAITING_HOUR with day value {day_value}")
                else:
                    # Send the day selection list again
                    await send_day_selection_message(
                        phone_number, 
                        "No pude entender tu selección. Por favor, selecciona un día de la semana:"
                    )
                    return {"status": "success"}
                
        elif current_state == STATES["AWAITING_HOUR"]:
            # User responding with preferred hour
            try:
                hour = int(message_body.strip())
                if 0 <= hour <= 23:
                    temp_data = user_state["temp_data"]
                    preferred_day = temp_data.get("preferred_day", 0)
                    
                    # Update user preferences
                    crud.update_user_preferences(db, user.id, preferred_day, hour)
                    logger.info(f"[{request_id}] Updated user preferences: day={preferred_day}, hour={hour}")
                    
                    # Days mapped to names for better UX
                    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
                    day_name = days[preferred_day]
                    
                    response_message = (
                        f"¡Perfecto! Recibirás preguntas médicas cada {day_name} a las {hour}:00 horas. "
                        "Para dejar de recibir preguntas, escribe DETENER en cualquier momento."
                    )
                    set_user_state(phone_number, STATES["SUBSCRIBED"])
                    
                    # Send a sample question right away to demonstrate
                    background_tasks.add_task(send_sample_question, phone_number, db)
                else:
                    response_message = "Por favor, elige un número del 0 al 23."
            except ValueError:
                response_message = "Por favor, responde con un número del 0 al 23."
                
        elif current_state == STATES["SUBSCRIBED"] or current_state == STATES["AWAITING_QUESTION_RESPONSE"]:
            # User already subscribed, check for commands or answering a question
            if message_body.lower() in ["detener", "stop", "unsubscribe"]:
                crud.deactivate_user(db, user.id)
                response_message = "Has cancelado tu suscripción. Ya no recibirás preguntas médicas. Para volver a suscribirte, escribe INICIAR."
                set_user_state(phone_number, STATES["INITIAL"])
            elif message_body.lower() in ["iniciar", "start", "subscribe"]:
                # Send the welcome button message again
                await send_simple_button_message(
                    phone_number,
                    "¿Deseas recibir preguntas médicas semanales para reforzar tus conocimientos?",
                    "Configuración de suscripción"
                )
                set_user_state(phone_number, STATES["AWAITING_CONFIRMATION"])
                return {"status": "success"}
            elif re.match(r'^\d+$', message_body.strip()) and current_state == STATES["AWAITING_QUESTION_RESPONSE"]:
                # User is responding to a question
                is_correct, feedback = process_user_response(db, user.id, message_body)
                response_message = feedback
                set_user_state(phone_number, STATES["SUBSCRIBED"])
            else:
                response_message = (
                    "Recuerda que puedes utilizar estos comandos:\n"
                    "DETENER - para dejar de recibir preguntas\n"
                    "INICIAR - para configurar de nuevo tus preferencias"
                )
        
        # Send response to the user
        if response_message:
            logger.info(f"[{request_id}] Sending response: {response_message}")
            send_result = await whatsapp_client.send_message(phone_number, response_message)
            logger.info(f"[{request_id}] Message send result: {send_result}")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"[{request_id}] Error processing webhook: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

@log_execution_time
async def send_sample_question(phone_number: str, db: Session, request_id: str = None):
    """
    Send a sample question to demonstrate the bot functionality
    
    Args:
        phone_number: The user's phone number
        db: Database session
        request_id: Request ID for consistent logging
    """
    logger.info(f"[{request_id}] Preparing sample question for {phone_number}")
    
    try:
        # Get a random question
        from sqlalchemy.sql.expression import func
        question = db.query(models.Question).order_by(func.random()).first()
        
        if not question:
            # No questions in database, send a default one
            logger.info(f"[{request_id}] No questions found in database, using default question")
            question_text = (
                "Pregunta de ejemplo: ¿Cuál de las siguientes condiciones es una contraindicación absoluta para el uso de trombolíticos en un paciente con infarto agudo de miocardio?\n\n"
                "1) Hipertensión arterial controlada\n"
                "2) Sangrado intracraneal previo\n"
                "3) Diabetes mellitus\n"
                "4) Edad mayor de 75 años"
            )
            # Correct answer would be 2
        else:
            # Format the question with options
            logger.info(f"[{request_id}] Using question ID: {question.id}, Category: {question.category}")
            options = []
            correct_option = 0
            
            for i, option in enumerate(question.options):
                options.append(f"{i+1}) {option}")
                if i+1 == question.correct_option:
                    correct_option = i+1
            
            question_text = f"{question.text}\n\n" + "\n".join(options)
        
        # Get the user from the database
        user = crud.get_user_by_phone(db, phone_number)
        if user:
            # Set user state to waiting for question response
            set_user_state(phone_number, STATES["AWAITING_QUESTION_RESPONSE"])
            logger.info(f"[{request_id}] Set user state to AWAITING_QUESTION_RESPONSE")
            
            # Prepare message with question
            message = f"¡Aquí tienes una pregunta de ejemplo!\n\n{question_text}\n\nResponde con el número de la opción que consideres correcta."
            
            # Send the question
            logger.info(f"[{request_id}] Sending question to {phone_number}")
            result = await whatsapp_client.send_message(
                phone_number,
                message
            )
            
            logger.info(f"[{request_id}] Question message send result: {result}")
            return result
        else:
            logger.warning(f"[{request_id}] User not found for phone number: {phone_number}")
            return False
    
    except Exception as e:
        logger.error(f"[{request_id}] Error sending sample question: {str(e)}", exc_info=True)
        return False

@log_execution_time
async def send_day_selection_message(phone_number: str, message: str, request_id: str = None):
    """
    Send a day selection list message to the user.
    
    Args:
        phone_number: The user's phone number
        message: The message text to send with the list
        request_id: Request ID for consistent logging
    """
    logger.info(f"[{request_id}] Preparing day selection message for {phone_number}")
    
    # Create the sections array for the interactive list
    sections = [
        {
            "title": "Días de la semana",
            "rows": [
                {"id": "day_1", "title": "Lunes", "description": "Primer día de la semana"},
                {"id": "day_2", "title": "Martes", "description": "Segundo día de la semana"},
                {"id": "day_3", "title": "Miércoles", "description": "Tercer día de la semana"},
                {"id": "day_4", "title": "Jueves", "description": "Cuarto día de la semana"},
                {"id": "day_5", "title": "Viernes", "description": "Quinto día de la semana"},
                {"id": "day_6", "title": "Sábado", "description": "Sexto día de la semana"},
                {"id": "day_7", "title": "Domingo", "description": "Séptimo día de la semana"}
            ]
        }
    ]
    
    logger.info(f"[{request_id}] Sending interactive list message with {len(sections[0]['rows'])} options")
    
    # Send the interactive list message
    result = await whatsapp_client.send_interactive_list_message(
        to_number=phone_number,
        header_text="Selección de día",
        body_text=message,
        button_text="Ver días",
        sections=sections,
        footer_text="Banquea - Bot de preguntas médicas"
    )
    
    logger.info(f"[{request_id}] Interactive list message send result: {result}")
    return result

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
def load_questions(
    db: Session = Depends(get_db)
):
    """Admin endpoint to load questions from CSV files"""
    try:
        load_questions_from_csv(db)
        return {"status": "success", "message": "Questions loaded successfully"}
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading questions: {str(e)}")

@router.get("/admin/users")
def get_all_users(
    db: Session = Depends(get_db)
):
    """Admin endpoint to get all users"""
    users = db.query(models.User).all()
    return users

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
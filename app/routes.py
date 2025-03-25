from fastapi import APIRouter, Request, HTTPException
import logging
import json
from datetime import datetime
import random
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from .database import get_db
from .whatsapp import WhatsAppClient
from .utils import (
    get_random_question, process_user_response,
    load_all_data, questions_store
)
from . import crud

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

@router.get("/")
def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "questions_loaded": len(questions_store)}

@router.get("/webhook")
async def verify_webhook(request: Request):
    """Verify webhook for WhatsApp API"""
    try:
        logger.info(f"Received webhook verification request: {json.dumps(dict(request.query_params))}")
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
async def webhook(request: Request, db: Session = get_db()):
    """Handle WhatsApp webhook - this is the main entry point for all WhatsApp interactions"""
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
                # Check if this is a status update
                if "statuses" in value:
                    # Handle message status updates if needed
                    logger.info("Received status update")
                return {"status": "no messages"}
                
            message = value["messages"][0]
            phone_number = message["from"]
            
            # Get contact info if available
            name = None
            if "contacts" in value and value["contacts"]:
                contact = value["contacts"][0]
                if "profile" in contact:
                    name = contact["profile"].get("name")
            
            # Get or create user in database
            user = crud.get_user_by_phone(db, phone_number)
            if not user:
                user = crud.create_user(db, phone_number)
                # Set initial state for new users
                user.conversation_state = STATES["INITIAL"]
                db.commit()
            
            # Get current conversation state
            current_state = user.conversation_state
            
            # Handle different message types
            if message["type"] == "interactive":
                await handle_interactive_message(db, user, message)
            elif message["type"] == "text":
                await handle_text_message(db, user, message)
            else:
                # Send fallback message for unsupported message types
                await whatsapp_client.send_message(
                    phone_number,
                    "Lo siento, no puedo procesar este tipo de mensaje. Por favor, envía un mensaje de texto."
                )
            
            return {"status": "success"}
            
        except KeyError as e:
            logger.error(f"KeyError processing webhook: {str(e)}")
            return {"status": "error", "error": f"Missing field: {str(e)}"}
    
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

async def handle_interactive_message(db: Session, user, message):
    """Handle interactive message responses (buttons or list selections)"""
    phone_number = user.phone_number
    
    if "button_reply" in message["interactive"]:
        # Handle button replies (Yes/No responses)
        button_reply = message["interactive"]["button_reply"]
        button_id = button_reply["id"]
        
        if user.conversation_state == STATES["AWAITING_CONFIRMATION"]:
            if button_id == "yes_button":
                # Check if this is a returning user (with day and hour already set)
                if user.preferred_day is not None and user.preferred_hour is not None:
                    # Returning user with preferences already set - send question immediately
                    await send_random_question(db, user)
                else:
                    # First-time user - move to day selection
                    user.conversation_state = STATES["AWAITING_DAY"]
                    db.commit()
                    
                    # Send day selection list (not template)
                    await whatsapp_client.send_day_selection_message(
                        phone_number,
                        "Por favor selecciona el día de la semana en que deseas recibir las preguntas:"
                    )
            elif button_id == "no_button":
                # User declined, send goodbye message
                await whatsapp_client.send_message(
                    phone_number,
                    "Entendido. Si cambias de opinión, escribe 'hola' para comenzar nuevamente."
                )
                # Reset state
                user.conversation_state = STATES["INITIAL"]
                db.commit()
        else:
            # Handle unexpected button reply
            await send_fallback_message(db, user)
    
    elif "list_reply" in message["interactive"]:
        # Handle list replies (day selection or question answers)
        list_reply = message["interactive"]["list_reply"]
        selection_id = list_reply["id"]
        selection_title = list_reply["title"]
        
        if user.conversation_state == STATES["AWAITING_DAY"]:
            # Handle day selection
            # Extract day from selection_id (format: "day_X" where X is 0-6)
            if selection_id.startswith("day_"):
                try:
                    selected_day = int(selection_id.split("_")[1])
                    
                    # Store selected day
                    user.preferred_day = selected_day
                    user.conversation_state = STATES["AWAITING_HOUR"]
                    db.commit()
                    
                    # Ask for hour selection
                    await whatsapp_client.send_message(
                        phone_number,
                        "¿A qué hora del día te gustaría recibir las preguntas? Por favor, indica la hora en formato de 24 horas (0-23)."
                    )
                except (ValueError, IndexError):
                    await send_fallback_message(db, user)
            else:
                await send_fallback_message(db, user)
                
        elif user.conversation_state == STATES["AWAITING_QUESTION_RESPONSE"]:
            # Handle question response
            # Format: q_{question_id}_opt_{option_number}
            parts = selection_id.split("_")
            if len(parts) >= 4 and parts[0] == "q" and parts[2] == "opt":
                try:
                    question_id = int(parts[1])
                    option_num = int(parts[3])
                    
                    # Process response
                    is_correct, feedback = process_user_response(phone_number, question_id, option_num)
                    
                    # Send feedback
                    await whatsapp_client.send_message(phone_number, feedback)
                    
                    # Update state
                    user.conversation_state = STATES["SUBSCRIBED"]
                    user.last_question_answered = datetime.utcnow()
                    db.commit()
                except (ValueError, IndexError):
                    await send_fallback_message(db, user)
            else:
                await send_fallback_message(db, user)
        else:
            # Handle unexpected list reply
            await send_fallback_message(db, user)

async def handle_text_message(db: Session, user, message):
    """Handle text message responses"""
    phone_number = user.phone_number
    text = message["text"]["body"].strip().lower()
    
    # Special commands
    if text == "%%force_new_question":
        # Force send a new question regardless of state
        await send_random_question(db, user)
        return
    
    # Handle based on conversation state
    if user.conversation_state == STATES["INITIAL"]:
        # Initial greeting / start command
        if text in ["hola", "hello", "hi", "inicio", "start", "comenzar"]:
            # Check if this is a returning user with previous answers
            user_has_previous_answers = db.query(crud.models.UserResponse).filter(
                crud.models.UserResponse.user_id == user.id
            ).count() > 0
            
            if user_has_previous_answers:
                # Returning user - send confirmation template
                await whatsapp_client.send_template_message(
                    phone_number,
                    "confirmacion_pregunta",
                    "es"
                )
            else:
                # First-time user - send welcome template
                await whatsapp_client.send_template_message(
                    phone_number,
                    "bienvenida_banquea",
                    "es"
                )
            
            user.conversation_state = STATES["AWAITING_CONFIRMATION"]
            db.commit()
        else:
            # Send a standard greeting for any other message
            await whatsapp_client.send_message(
                phone_number, 
                "¡Hola! Soy el bot de Banquea. Escribe 'hola' para comenzar."
            )
    
    elif user.conversation_state == STATES["AWAITING_HOUR"]:
        # Process hour selection
        try:
            hour = int(text)
            if 0 <= hour <= 23:
                # Valid hour, store it
                user.preferred_hour = hour
                user.conversation_state = STATES["SUBSCRIBED"]
                db.commit()
                
                # Confirmation message
                day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                await whatsapp_client.send_message(
                    phone_number,
                    f"¡Perfecto! Recibirás preguntas cada {day_names[user.preferred_day]} a las {hour}:00 horas. "
                    f"Para recibir una pregunta ahora, envía '%%force_new_question'."
                )
                
                # Send a first question immediately
                await send_random_question(db, user)
            else:
                await whatsapp_client.send_message(
                    phone_number,
                    "Por favor, indica una hora válida entre 0 y 23."
                )
        except ValueError:
            await whatsapp_client.send_message(
                phone_number,
                "Por favor, indica la hora como un número entre 0 y 23."
            )
    
    elif user.conversation_state == STATES["SUBSCRIBED"]:
        # User is subscribed, sending a random message
        await whatsapp_client.send_message(
            phone_number,
            "Recibirás una pregunta médica en el horario programado. "
            "Si deseas recibir una pregunta ahora, envía '%%force_new_question'."
        )
    
    else:
        # For any other state, send fallback
        await send_fallback_message(db, user)

async def send_random_question(db: Session, user):
    """Send a random question to the user"""
    phone_number = user.phone_number
    
    question = get_random_question()
    if question:
        # Update user state
        user.conversation_state = STATES["AWAITING_QUESTION_RESPONSE"]
        user.last_question_id = question["id"]
        user.last_message_sent = datetime.utcnow()
        db.commit()
        
        # Send question
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

async def send_fallback_message(db: Session, user):
    """Send fallback message when we don't understand the user's input"""
    phone_number = user.phone_number
    
    await whatsapp_client.send_message(
        phone_number,
        "Lo siento, no entiendo tu mensaje. "
        "Si deseas recibir una pregunta médica, escribe '%%force_new_question'."
    ) 
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import pytz

from .models import User, UserState, UserQuestion
from .whatsapp import WhatsAppClient
from . import crud
from .questions import question_manager
from .active_users import active_user_manager

logger = logging.getLogger(__name__)

# Create WhatsApp client instance
whatsapp_client = WhatsAppClient()

# Spanish day name to numeric day of week mapping (0 = Monday, 6 = Sunday)
DAY_MAPPING = {
    "Lunes": 0,
    "Martes": 1,
    "Miércoles": 2,
    "Miercoles": 2,  # Handle without accent
    "Jueves": 3,
    "Viernes": 4,
    "Sábado": 5,
    "Sabado": 5,  # Handle without accent
    "Domingo": 6
}

# Day of week to Spanish day name mapping (for display in confirmation messages)
DAY_NAMES = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo"
}

async def handle_message(db: Session, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main message handler - processes incoming messages based on user state
    
    Args:
        db: Database session
        message: Processed message data from webhook
        
    Returns:
        Dict with processing result
    """
    # Ignore non-message events (like status updates)
    if message.get("type") != "message":
        logger.info(f"Ignoring non-message event: {message.get('type')}")
        return {"status": "ignored", "reason": "not_a_message"}
    
    from_number = message.get("from_number")

            # Check for special command to get a new question
    if message_type == "text" and body.strip() == "%%get_new_question$$":
        return await handle_force_new_question(db, user)
    
    # Only process messages from active users
    if not active_user_manager.is_active(from_number):
        logger.info(f"Ignoring message from inactive number: {from_number}")
        return {"status": "ignored", "reason": "inactive_user"}
    message_type = message.get("message_type")
    body = message.get("body", "")
    
    if not from_number:
        logger.error("Message missing sender phone number")
        return {"status": "error", "reason": "missing_phone_number"}
    
    logger.info(f"Processing message from {from_number}: {body[:50]}...")
    
    # Get or create user from database
    user = crud.get_user_by_phone(db, from_number)
    if not user:
        logger.warning(f"Received message from unknown user: {from_number}")
        return {"status": "error", "reason": "unknown_user"}
    
    # Update whatsapp_id if not set
    if not user.whatsapp_id:
        user.whatsapp_id = from_number
        db.commit()
        logger.info(f"Updated WhatsApp ID for user {from_number}")
    

    # Process message based on user state
    if user.state == UserState.UNCONTACTED:
        return await handle_uncontacted_user(db, user, message)
    elif user.state == UserState.AWAITING_DAY:
        return await handle_day_selection(db, user, message)
    elif user.state == UserState.AWAITING_HOUR:
        return await handle_hour_selection(db, user, message)
    elif user.state == UserState.AWAITING_QUESTION_CONFIRMATION:
        return await handle_question_confirmation(db, user, message)
    elif user.state == UserState.AWAITING_QUESTION_RESPONSE:
        return await handle_question_response(db, user, message)
    elif user.state == UserState.SUBSCRIBED:
        # Handle subscribed user state
        logger.info(f"User {user.phone_number} is in SUBSCRIBED state. No specific action required.")
        return {"status": "success", "action": "no_action_needed"}
    else:
        logger.error(f"Unknown user state: {user.state} for user {from_number}")
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="Lo siento, ha ocurrido un error. Por favor, intente más tarde."
        )
        return {"status": "error", "reason": "unknown_state"}

async def handle_uncontacted_user(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a message from a user in UNCONTACTED state.
    Send the initial welcome messages and update state.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message data
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    logger.info(f"Handling message from uncontacted user: {from_number}")
    
    # Send welcome template message
    success = await whatsapp_client.send_template_message(
        to_number=from_number,
        template_name="primer_contacto"
    )
    
    if not success:
        logger.error(f"Failed to send welcome template to {from_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    # Update user state
    user.state = UserState.AWAITING_DAY
    db.commit()
    
    logger.info(f"Updated user {from_number} state to AWAITING_DAY")
    return {"status": "success", "action": "sent_welcome_and_day_selection"}

async def handle_day_selection(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle day selection from a user in AWAITING_DAY state.
    Parse the day, save it to DB, and send hour selection template.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message data
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    body = message.get("body", "").strip()
    
    logger.info(f"Processing day selection from {from_number}: '{body}'")
    
    # Validate day name
    if body not in DAY_MAPPING:
        # Send error message
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="El día seleccionado no es válido. Por favor, escribe el nombre del día con la primera letra en mayúscula (por ejemplo: Lunes, Martes, etc.)."
        )
        logger.warning(f"Invalid day name from {from_number}: '{body}'")
        return {"status": "error", "reason": "invalid_day"}
    
    # Save selected day to database
    day_number = DAY_MAPPING[body]
    user.scheduled_day_of_week = day_number
    user.state = UserState.AWAITING_HOUR
    db.commit()
    
    logger.info(f"User {from_number} selected day: {body} (index: {day_number})")
    
    # Send hour selection template
    success = await whatsapp_client.send_template_message(
        to_number=from_number,
        template_name="seleccion_hora_minuto"
    )
    
    if not success:
        logger.error(f"Failed to send hour selection template to {from_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    return {"status": "success", "action": "processed_day", "selected_day": body}

async def handle_hour_selection(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle hour selection from a user in AWAITING_HOUR state.
    Parse the hour in HH:MM format, save it to DB, send confirmation, and update state.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message data
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    body = message.get("body", "").strip()
    
    logger.info(f"Processing hour selection from {from_number}: '{body}'")
    
    # Validate hour format (HH:MM)
    try:
        # Attempt to parse HH:MM format
        time_parts = body.split(':')
        if len(time_parts) != 2:
            raise ValueError("Invalid format, expected HH:MM")
            
        hour_str, minute_str = time_parts
        hour = int(hour_str)
        minute = int(minute_str) # Validate minute part as well
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Hour or minute out of range")
            
    except ValueError as e:
        # Send error message
        error_message = "La hora seleccionada no es válida. Por favor, ingresa la hora en formato HH:MM (por ejemplo, 09:30 o 14:00)."
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text=error_message
        )
        logger.warning(f"Invalid time format from {from_number}: '{body}'. Error: {e}")
        return {"status": "error", "reason": "invalid_hour_format"}
    
    # Save selected hour and minute to database
    user.scheduled_hour = hour
    user.scheduled_minute = minute # Save the minute
    user.state = UserState.SUBSCRIBED
    db.commit()
    
    logger.info(f"User {from_number} selected time: {hour:02d}:{minute:02d} (Day: {user.scheduled_day_of_week})")
    
    # Get day name for confirmation message
    day_name = DAY_NAMES.get(user.scheduled_day_of_week, "día desconocido")
    
    # Send confirmation message (using the selected hour and minute)
    confirmation_msg = (
        f"¡Perfecto! Has programado recibir tus preguntas cada {day_name} a las {hour:02d}:{minute:02d} horas. "
        f"Recibirás tu primera pregunta en el próximo horario programado. "
        f"¡Gracias por suscribirte!"
    )
    
    await whatsapp_client.send_text_message(
        to_number=from_number,
        message_text=confirmation_msg
    )
    
    # Schedule the first question confirmation
    from .scheduler import schedule_next_question
    next_time = schedule_next_question(user, db)
    
    return {
        "status": "success", 
        "action": "processed_hour", 
        "selected_time": f"{hour:02d}:{minute:02d}", # Return full time
        "next_scheduled": next_time.isoformat() if next_time else None
    }

async def handle_question_confirmation(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle confirmation response before sending a question.
    Processes the user's choice whether they want to receive a question now.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message data
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    body = message.get("body", "").strip()
    message_type = message.get("message_type")
    
    logger.info(f"Processing question confirmation from {from_number}: '{body}'")
    
    # Extract the response - it could be a button or text
    user_response = body.lower()
    
    # Check for button response type
    if message_type == "button":
        payload = message.get("interactive_data", {}).get("payload", "")
        if payload:
            user_response = payload.lower()
    
    # Handle the confirmation response
    # Check if the response indicates readiness (accept the specific payload)
    if user_response in ["estoy listo reforzar", "Estoy listo para reforzar", "estoy listo para reforzar", "si", "sí", "ok"]:
        logger.info(f"User {from_number} confirmed to receive a question")
        
        # Import here to avoid circular import
        from .scheduler import send_random_question
        
        # Send a question immediately (no need for db session here, send_random_question creates its own)
        await send_random_question(user.id)
        
        return {"status": "success", "action": "sending_question"}
    
    # Handle negative confirmation or unrecognized response
    elif user_response in ["Hoy no quiero repasar", "hoy no quiero repasar", "no", "no quiero", "no quiero repasar", "no quiero reforzar"]:
        logger.info(f"User {from_number} declined to receive a question now")
        # Reschedule for the next planned time
        user.state = UserState.SUBSCRIBED # Put back into subscribed state
        db.commit()
        from .scheduler import schedule_next_question
        next_time = schedule_next_question(user, db)
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="Entendido. Te preguntaré de nuevo en tu próximo horario programado."
        )
        return {"status": "success", "action": "confirmation_declined", "next_scheduled": next_time.isoformat() if next_time else None}
        
    else:
        # Unrecognized response
        logger.warning(f"Unrecognized confirmation response from {from_number}: '{body}' (parsed as '{user_response}')")
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="Lo siento, no entendí tu respuesta. Por favor, selecciona una de las opciones."
        )
        # Keep user in AWAITING_QUESTION_CONFIRMATION state
        return {"status": "error", "reason": "unrecognized_confirmation"}

async def handle_question_response(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle user's response to a medical question.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message data
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    message_type = message.get("message_type")
    interactive_data = message.get("interactive_data", {})
    
    logger.info(f"Processing question response from {from_number}")
    
    # Get the most recent unanswered question for this user
    last_question = db.query(UserQuestion).filter(
        UserQuestion.user_id == user.id,
        UserQuestion.answered_at.is_(None)
    ).order_by(UserQuestion.sent_at.desc()).first()
    
    if not last_question:
        logger.warning(f"No pending question found for user {from_number}")
        
        # Update user state
        user.state = UserState.SUBSCRIBED
        db.commit()
        
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="Lo siento, no encontré una pregunta pendiente. Recibirás tu próxima pregunta en el horario programado."
        )
        
        return {"status": "error", "reason": "no_pending_question"}
    
    # Handle interactive list response
    if message_type == "interactive" and interactive_data:
        reply_type = interactive_data.get("reply_type")
        
        if reply_type == "list_reply":
            answer_id = interactive_data.get("id")
            answer_title = interactive_data.get("title")
            
            if not answer_id or not answer_title:
                logger.warning(f"Invalid list reply from {from_number}: {interactive_data}")
                return {"status": "error", "reason": "invalid_list_reply"}
            
            # Record the answer
            last_question.user_answer = answer_title
            last_question.answered_at = datetime.now(pytz.timezone('America/Lima'))
            last_question.is_correct = (answer_id == last_question.correct_answer_id)
            
            # Update user state
            user.state = UserState.SUBSCRIBED
            db.commit()
            
            logger.info(f"User {from_number} answered question {last_question.question_id}: " + 
                       f"'{answer_title}' - Correct: {last_question.is_correct}")
            
            # Send feedback based on correctness
            if last_question.is_correct:
                await whatsapp_client.send_text_message(
                    to_number=from_number,
                    message_text="¡Respuesta correcta! 🎉 Muy bien. Recibirás tu próxima pregunta en el horario programado."
                )
            else:
                await whatsapp_client.send_text_message(
                    to_number=from_number,
                    message_text=f"Tu respuesta fue incorrecta. La respuesta correcta es: {last_question.correct_answer}\n\n" +
                                f"Recibirás tu próxima pregunta en el horario programado."
                )
            # Incluir comentarios AI (discusión, justificación y fuente)
            ai_info = question_manager.ai_data.get(last_question.question_id, {})
            discussion = ai_info.get('discussion_ai')
            justification = ai_info.get('justification_ai')
            source = ai_info.get('source_ai')
            if discussion or justification or source:
                ai_message = ''
                if discussion:
                    ai_message += f"Discusión: {discussion}\n"
                if justification:
                    ai_message += f"Justificación: {justification}\n"
                if source:
                    ai_message += f"Fuente: {source}"
                await whatsapp_client.send_text_message(
                    to_number=from_number,
                    message_text=ai_message
                )
            
            # Schedule next question
            from .scheduler import schedule_next_question
            next_time = schedule_next_question(user, db)
            
            return {
                "status": "success",
                "action": "processed_answer",
                "is_correct": last_question.is_correct,
                "next_scheduled": next_time.isoformat()
            }
    
    # Unrecognized response format
    logger.warning(f"Unrecognized question response format from {from_number}: {message_type}")
    
    await whatsapp_client.send_text_message(
        to_number=from_number,
        message_text="Lo siento, no pude procesar tu respuesta. Por favor, selecciona una opción de la lista proporcionada."
    )
    
    return {"status": "error", "reason": "invalid_response_format"}

async def handle_force_new_question(db: Session, user: User) -> Dict[str, Any]:
    """
    Handle special command to force sending a new question.
    
    Args:
        db: Database session
        user: User model instance
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    logger.info(f"Handling force new question command from {from_number}")
    
    # Only allow this command for subscribed users
    if user.state not in [UserState.SUBSCRIBED, UserState.AWAITING_QUESTION_CONFIRMATION]:
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="Lo siento, este comando solo está disponible después de completar la configuración inicial."
        )
        return {"status": "error", "reason": "invalid_state_for_command"}
    
    # Import here to avoid circular import
    from .scheduler import send_random_question
    
    # Send a question directly without changing the schedule
    # Pass only user.id as send_random_question creates its own DB session
    await send_random_question(user.id)
    
    return {"status": "success", "action": "forced_new_question"}

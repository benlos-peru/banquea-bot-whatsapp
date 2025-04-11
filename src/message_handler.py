import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .models import User, UserState
from .whatsapp import WhatsAppClient
from . import crud

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
    elif user.state == UserState.SUBSCRIBED:
        return await handle_subscribed_user(db, user, message)
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
        template_name="bienvenida"
    )
    
    if not success:
        logger.error(f"Failed to send welcome template to {from_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    # Send day selection template
    success = await whatsapp_client.send_template_message(
        to_number=from_number,
        template_name="seleccion_dia"
    )
    
    if not success:
        logger.error(f"Failed to send day selection template to {from_number}")
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
        template_name="seleccion_hora"
    )
    
    if not success:
        logger.error(f"Failed to send hour selection template to {from_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    return {"status": "success", "action": "processed_day", "selected_day": body}

async def handle_hour_selection(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle hour selection from a user in AWAITING_HOUR state.
    Parse the hour, save it to DB, send confirmation, and update state.
    
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
    
    # Validate hour format
    try:
        hour = int(body)
        if hour < 0 or hour > 23:
            raise ValueError("Hour out of range")
    except ValueError:
        # Send error message
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message_text="La hora seleccionada no es válida. Por favor, ingresa un número entre 0 y 23."
        )
        logger.warning(f"Invalid hour from {from_number}: '{body}'")
        return {"status": "error", "reason": "invalid_hour"}
    
    # Save selected hour to database
    user.scheduled_hour = hour
    user.state = UserState.SUBSCRIBED
    db.commit()
    
    logger.info(f"User {from_number} selected hour: {hour}")
    
    # Get day name for confirmation message
    day_name = DAY_NAMES.get(user.scheduled_day_of_week, "día desconocido")
    
    # Send confirmation message
    confirmation_msg = (
        f"¡Perfecto! Has programado recibir tus preguntas cada {day_name} a las {hour}:00 horas. "
        f"Recibirás tu primera pregunta en el próximo horario programado. "
        f"¡Gracias por suscribirte!"
    )
    
    await whatsapp_client.send_text_message(
        to_number=from_number,
        message_text=confirmation_msg
    )
    
    return {"status": "success", "action": "processed_hour", "selected_hour": hour}

async def handle_subscribed_user(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle messages from already subscribed users.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message data
        
    Returns:
        Dict with processing result
    """
    from_number = user.phone_number
    body = message.get("body", "").strip().lower()
    
    logger.info(f"Message from subscribed user {from_number}: '{body}'")
    
    # For now, just acknowledge the message
    await whatsapp_client.send_text_message(
        to_number=from_number,
        message_text="Gracias por tu mensaje. Recibirás tus preguntas según tu horario programado."
    )
    
    return {"status": "success", "action": "acknowledged_message"}

from sqlalchemy.orm import Session
import logging
from typing import Dict, Any

from .models import User, UserState
from .crud import get_user_by_phone, create_user, update_user
from .whatsapp import whatsapp_client

logger = logging.getLogger(__name__)

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

async def handle_message(db: Session, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main message handler - routes messages based on user state
    
    Args:
        db: Database session
        message: Processed message from webhook
        
    Returns:
        Dict with response information
    """
    if message.get("type") != "message":
        logger.info(f"Ignoring non-message webhook: {message.get('type')}")
        return {"status": "ignored", "reason": "not a message"}
    
    from_number = message.get("from_number")
    message_type = message.get("message_type")
    body = message.get("body", "")
    
    logger.info(f"Handling message from {from_number}: {body[:50]}")
    
    # Get or create user
    user = get_user_by_phone(db, from_number)
    if not user:
        user = create_user(db, phone_number=from_number, whatsapp_id=from_number)
        logger.info(f"Created new user with phone number {from_number}")
    
    # Update whatsapp_id if not set
    if not user.whatsapp_id:
        user.whatsapp_id = from_number
        db.commit()
        logger.info(f"Updated whatsapp_id for user {from_number}")
    
    # Handle based on user state
    if user.state == UserState.UNCONTACTED:
        return await handle_uncontacted_user(db, user, message)
    elif user.state == UserState.AWAITING_DAY:
        return await handle_day_selection(db, user, message)
    elif user.state == UserState.AWAITING_HOUR:
        return await handle_hour_selection(db, user, message)
    elif user.state == UserState.SUBSCRIBED:
        return await handle_subscribed_user(db, user, message)
    elif user.state == UserState.AWAITING_RESPONSE:
        return await handle_question_response(db, user, message)
    else:
        logger.warning(f"Unknown user state: {user.state} for user {from_number}")
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message="Lo siento, ha ocurrido un error. Por favor, intenta nuevamente más tarde."
        )
        return {"status": "error", "reason": "unknown_state"}

async def handle_uncontacted_user(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a message from a user in UNCONTACTED state.
    A user in this state should receive welcome messages.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message from webhook
    
    Returns:
        Dict with response information
    """
    logger.info(f"Handling uncontacted user: {user.phone_number}")
    
    # Send welcome template message
    success = await whatsapp_client.send_template_message(
        to_number=user.phone_number,
        template_name="bienvenida"
    )
    
    if not success:
        logger.error(f"Failed to send welcome template to {user.phone_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    # Send day selection template
    success = await whatsapp_client.send_template_message(
        to_number=user.phone_number,
        template_name="seleccion_dia"
    )
    
    if not success:
        logger.error(f"Failed to send day selection template to {user.phone_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    # Update user state to AWAITING_DAY
    user.state = UserState.AWAITING_DAY
    db.commit()
    logger.info(f"Updated user {user.phone_number} state to AWAITING_DAY")
    
    return {"status": "success", "action": "contacted"}

async def handle_day_selection(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a message from a user in AWAITING_DAY state.
    Process the day selection and move to hour selection.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message from webhook
    
    Returns:
        Dict with response information
    """
    from_number = user.phone_number
    body = message.get("body", "").strip()
    
    logger.info(f"Handling day selection from {from_number}: {body}")
    
    # Validate day name
    if body not in DAY_MAPPING:
        logger.warning(f"Invalid day name received: {body}")
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message="Lo siento, no reconozco ese día. Por favor, escribe el nombre del día con la primera letra en mayúscula (por ejemplo: Lunes, Martes, etc.)."
        )
        return {"status": "error", "reason": "invalid_day"}
    
    # Convert day name to numeric day of week
    day_of_week = DAY_MAPPING[body]
    
    # Update user's scheduled day
    user.scheduled_day_of_week = day_of_week
    user.state = UserState.AWAITING_HOUR
    db.commit()
    
    logger.info(f"Updated user {from_number} scheduled day to {day_of_week}")
    
    # Send hour selection template
    success = await whatsapp_client.send_template_message(
        to_number=from_number,
        template_name="seleccion_hora"
    )
    
    if not success:
        logger.error(f"Failed to send hour selection template to {from_number}")
        return {"status": "error", "reason": "template_send_failed"}
    
    return {"status": "success", "action": "day_selected", "day": day_of_week}

async def handle_hour_selection(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a message from a user in AWAITING_HOUR state.
    Process the hour selection and update subscription status.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message from webhook
    
    Returns:
        Dict with response information
    """
    from_number = user.phone_number
    body = message.get("body", "").strip()
    
    logger.info(f"Handling hour selection from {from_number}: {body}")
    
    # Validate hour format
    try:
        hour = int(body)
        if hour < 0 or hour > 23:
            raise ValueError("Hour out of range")
    except ValueError:
        logger.warning(f"Invalid hour received: {body}")
        await whatsapp_client.send_text_message(
            to_number=from_number,
            message="Lo siento, la hora debe ser un número entre 0 y 23. Por favor, intenta nuevamente."
        )
        return {"status": "error", "reason": "invalid_hour"}
    
    # Update user's scheduled hour
    user.scheduled_hour = hour
    user.state = UserState.SUBSCRIBED
    db.commit()
    
    logger.info(f"Updated user {from_number} scheduled hour to {hour}")
    
    # Convert day to Spanish name for confirmation message
    day_names = {v: k for k, v in DAY_MAPPING.items()}
    day_name = day_names.get(user.scheduled_day_of_week, "día desconocido")
    
    # Send confirmation message
    confirmation_message = (
        f"¡Perfecto! Has programado recibir tus preguntas cada {day_name} a las {hour}:00 horas. "
        f"Recibirás tu primera pregunta en el próximo horario programado. "
        f"¡Gracias por suscribirte!"
    )
    
    success = await whatsapp_client.send_text_message(
        to_number=from_number,
        message=confirmation_message
    )
    
    if not success:
        logger.error(f"Failed to send confirmation message to {from_number}")
        return {"status": "error", "reason": "message_send_failed"}
    
    return {"status": "success", "action": "hour_selected", "hour": hour}

async def handle_subscribed_user(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a message from a user in SUBSCRIBED state.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message from webhook
    
    Returns:
        Dict with response information
    """
    from_number = user.phone_number
    body = message.get("body", "").strip().lower()
    
    logger.info(f"Handling message from subscribed user {from_number}: {body}")
    
    # For now, just send a simple response
    await whatsapp_client.send_text_message(
        to_number=from_number,
        message="Gracias por tu mensaje. Recibirás tus preguntas en el horario programado."
    )
    
    return {"status": "success", "action": "acknowledged"}

async def handle_question_response(db: Session, user: User, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a message from a user in AWAITING_RESPONSE state.
    This is a placeholder for future implementation.
    
    Args:
        db: Database session
        user: User model instance
        message: Processed message from webhook
    
    Returns:
        Dict with response information
    """
    # This will be implemented in the future
    logger.info(f"Question response handling not yet implemented for user {user.phone_number}")
    
    await whatsapp_client.send_text_message(
        to_number=user.phone_number,
        message="Gracias por tu respuesta. Este flujo será implementado próximamente."
    )
    
    # Reset state to SUBSCRIBED
    user.state = UserState.SUBSCRIBED
    db.commit()
    
    return {"status": "success", "action": "response_acknowledged"}

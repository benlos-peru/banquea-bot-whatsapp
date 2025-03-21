from sqlalchemy.orm import Session
import datetime
from typing import Optional, List

from . import models, schemas

def get_user_by_phone(db: Session, phone_number: str) -> Optional[models.User]:
    """
    Get a user by phone number.
    
    Args:
        db: Database session
        phone_number: The user's phone number
        
    Returns:
        User model or None if not found
    """
    return db.query(models.User).filter(models.User.phone_number == phone_number).first()

def create_user(db: Session, phone_number: str) -> models.User:
    """
    Create a new user with the given phone number.
    
    Args:
        db: Database session
        phone_number: The user's phone number
        
    Returns:
        Newly created User model
    """
    db_user = models.User(
        phone_number=phone_number,
        is_active=True,
        is_blacklisted=False,
        created_at=datetime.datetime.utcnow()
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_preferences(
    db: Session, 
    user_id: int, 
    preferred_day: int, 
    preferred_hour: int
) -> models.User:
    """
    Update a user's preferences for when to receive messages.
    
    Args:
        db: Database session
        user_id: The user's ID
        preferred_day: Day of week (0-6 where 0 is Monday)
        preferred_hour: Hour of day (0-23)
        
    Returns:
        Updated User model
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if user:
        user.preferred_day = preferred_day
        user.preferred_hour = preferred_hour
        db.commit()
        db.refresh(user)
    
    return user

def deactivate_user(db: Session, user_id: int) -> models.User:
    """
    Deactivate a user (unsubscribe).
    
    Args:
        db: Database session
        user_id: The user's ID
        
    Returns:
        Updated User model
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if user:
        user.is_active = False
        db.commit()
        db.refresh(user)
    
    return user

def blacklist_user(db: Session, user_id: int) -> models.User:
    """
    Add a user to the blacklist.
    
    Args:
        db: Database session
        user_id: The user's ID
        
    Returns:
        Updated User model
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if user:
        user.is_blacklisted = True
        db.commit()
        db.refresh(user)
    
    return user

def get_user_responses(db: Session, user_id: int) -> List[models.UserResponse]:
    """
    Get all responses from a user.
    
    Args:
        db: Database session
        user_id: The user's ID
        
    Returns:
        List of UserResponse models
    """
    return db.query(models.UserResponse).filter(models.UserResponse.user_id == user_id).all()

def get_question_by_id(db: Session, question_id: int) -> Optional[models.Question]:
    """
    Get a question by ID.
    
    Args:
        db: Database session
        question_id: The question ID
        
    Returns:
        Question model or None if not found
    """
    return db.query(models.Question).filter(models.Question.id == question_id).first()

def get_options_for_question(db: Session, question_id: int) -> List[models.QuestionOption]:
    """
    Get all options for a question.
    
    Args:
        db: Database session
        question_id: The question ID
        
    Returns:
        List of QuestionOption models
    """
    return db.query(models.QuestionOption).filter(
        models.QuestionOption.question_id == question_id
    ).all() 
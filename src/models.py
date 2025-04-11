from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from .database import Base
import enum
from datetime import datetime

class UserState(enum.IntEnum):
    UNCONTACTED = 0
    AWAITING_DAY = 1
    AWAITING_HOUR = 2
    SUBSCRIBED = 3
    AWAITING_QUESTION_RESPONSE = 4
    AWAITING_QUESTION_CONFIRMATION = 5

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    username = Column(String)
    scheduled_hour = Column(Integer)  # 0-23
    scheduled_day_of_week = Column(Integer)  # 0-6 (Monday-Sunday)
    whatsapp_id = Column(String, unique=True)
    state = Column(Integer, default=UserState.UNCONTACTED)
    next_question_at = Column(DateTime, nullable=True)
    last_interaction_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to track questions sent to this user
    question_responses = relationship("UserQuestion", back_populates="user")

class UserQuestion(Base):
    """
    Model to track questions sent to users and their responses.
    """
    __tablename__ = "user_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    question_id = Column(Integer, index=True)  # ID from the questions CSV
    question_text = Column(Text)
    correct_answer = Column(String)
    correct_answer_id = Column(String)  # ID of the correct answer option
    sent_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)
    user_answer = Column(String, nullable=True)  # What the user answered
    is_correct = Column(Boolean, nullable=True)  # Whether their answer was correct
    
    # Relationship back to user
    user = relationship("User", back_populates="question_responses")

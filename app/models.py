from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    preferred_day = Column(Integer)  # 0-6 for Monday to Sunday
    preferred_hour = Column(Integer) # 0-23 hours
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_message_sent = Column(DateTime, nullable=True)
    is_blacklisted = Column(Boolean, default=False)
    conversation_state = Column(Integer, default=0)  # 0 = INITIAL state
    last_question_id = Column(Integer, nullable=True)
    last_question_answered = Column(DateTime, nullable=True)
    
    responses = relationship("UserResponse", back_populates="user")

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text)
    area = Column(String, nullable=True)
    
    options = relationship("QuestionOption", back_populates="question")
    responses = relationship("UserResponse", back_populates="question")

class QuestionOption(Base):
    __tablename__ = "question_options"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    text = Column(Text)
    is_correct = Column(Boolean, default=False)
    
    question = relationship("Question", back_populates="options")

class UserResponse(Base):
    __tablename__ = "user_responses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer)  # No longer a foreign key
    selected_option = Column(Integer)  # Store the option number instead of ID
    is_correct = Column(Boolean)
    responded_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="responses")
    # Remove relationship with Question 
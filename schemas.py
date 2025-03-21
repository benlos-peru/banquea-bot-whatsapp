from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

class UserBase(BaseModel):
    phone_number: str
    preferred_day: Optional[int] = None  # 0-6 (Monday to Sunday)
    preferred_hour: Optional[int] = None  # 0-23 hours

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime.datetime
    last_message_sent: Optional[datetime.datetime] = None
    is_blacklisted: bool

    class Config:
        from_attributes = True

class QuestionOptionBase(BaseModel):
    text: str
    is_correct: bool

class QuestionOptionCreate(QuestionOptionBase):
    pass

class QuestionOption(QuestionOptionBase):
    id: int
    question_id: int

    class Config:
        from_attributes = True

class QuestionBase(BaseModel):
    text: str
    area: Optional[str] = None

class QuestionCreate(QuestionBase):
    options: List[QuestionOptionCreate]

class Question(QuestionBase):
    id: int
    options: List[QuestionOption]

    class Config:
        from_attributes = True

class UserResponseBase(BaseModel):
    user_id: int
    question_id: int
    selected_option_id: int

class UserResponseCreate(UserResponseBase):
    pass

class UserResponse(UserResponseBase):
    id: int
    is_correct: bool
    responded_at: datetime.datetime

    class Config:
        from_attributes = True

class WhatsAppMessage(BaseModel):
    from_number: str = Field(..., alias="From")
    body: str = Field(..., alias="Body")
    
    class Config:
        populate_by_name = True 
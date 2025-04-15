from pydantic import BaseModel, Field
from typing import Optional

class UserBase(BaseModel):
    phone_number: str
    username: str
    scheduled_hour: int = Field(ge=0, le=23)
    scheduled_minute: int = Field(default=0, ge=0, le=59)
    scheduled_day_of_week: int = Field(ge=0, le=6)
    whatsapp_id: Optional[str] = None
    state: int = Field(default=0, ge=0, le=5)

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    phone_number: Optional[str] = None
    username: Optional[str] = None
    scheduled_hour: Optional[int] = Field(None, ge=0, le=23)
    scheduled_minute: Optional[int] = Field(None, ge=0, le=59)
    scheduled_day_of_week: Optional[int] = Field(None, ge=0, le=6)
    whatsapp_id: Optional[str] = None
    state: Optional[int] = Field(None, ge=0, le=5)

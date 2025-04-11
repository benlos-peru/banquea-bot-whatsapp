from sqlalchemy import Column, Integer, String, Enum
from .database import Base
import enum

class UserState(enum.IntEnum):
    UNCONTACTED = 0
    AWAITING_SCHEDULE = 1
    SUBSCRIBED = 2
    AWAITING_RESPONSE = 3

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    username = Column(String)
    scheduled_hour = Column(Integer)  # 0-23
    scheduled_day_of_week = Column(Integer)  # 0-6 (Monday-Sunday)
    whatsapp_id = Column(String, unique=True)
    state = Column(Integer, default=UserState.UNCONTACTED)

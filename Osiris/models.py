from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    # Every database table needs a Primary Key (a unique ID)
    id = Column(Integer, primary_key=True, index=True)
    
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String) # Notice we store hashed_password, NEVER plain text
    
    # Fitness Stats
    bmi = Column(Float)
    avatar_class = Column(String)
    rank = Column(String)
    xp = Column(Integer, default=0)
    streak = Column(Integer, default=0)
    last_activity_date = Column(DateTime, default=datetime.datetime.utcnow)

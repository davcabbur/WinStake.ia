from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True)
    
    # Financial/Gaming
    balance_fiat = Column(Float, default=0.0) # Saldo en FIAT (Euro/USD)
    
    # Security/KYC
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_kyc_verified = Column(Boolean, default=False) # Esencial para legalidad en España
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

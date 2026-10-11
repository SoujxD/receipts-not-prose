import uuid

from sqlalchemy import JSON, UUID, Column, DateTime, ForeignKey, String, Integer
from sqlalchemy.orm import relationship
import secrets

from database import Base


class Chat(Base):
    __tablename__ = "chat"

    id = Column(String(length=32), primary_key=True, index=True, default=secrets.token_urlsafe)
    created_at = Column(DateTime, index=True)
    messages = Column(JSON)
    form_submissions = relationship(
        "FormSubmission", cascade="all, delete", back_populates="chat"
    )

class FormSubmission(Base):
    __tablename__ = "form_submission"

    id = Column(String(length=32), primary_key=True, index=True, default=secrets.token_urlsafe)
    created_at = Column(DateTime, index=True)
    chat_id = Column(
        String(length=32), ForeignKey("chat.id"), index=True, nullable=False
    )
    chat = relationship("Chat", back_populates="form_submissions")
    name = Column(String, index=True)
    phone_number = Column(String, index=True)
    email = Column(String, index=True)
    status = Column(Integer, index=True)
    

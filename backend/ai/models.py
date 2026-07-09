"""
AI-specific SQLAlchemy models.

user_id columns use String(64) so they accept both legacy integer PKs and
Supabase UUIDs. No FK constraint on users.id so the AI conversation store
is independent of which auth system is in use.
"""
from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey
)
from datetime import datetime

from backend.models import Base  # reuse the same declarative Base


class AIConversation(Base):
    """Persistent log of user <-> assistant messages."""
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # 'user' | 'assistant' | 'system'
    message = Column(Text, nullable=False)
    meta = Column(Text, nullable=True)  # JSON string (language, tool calls, etc.)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AIReminder(Base):
    """Reminders scheduled by the AI (SMS + in-app)."""
    __tablename__ = "ai_reminders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    trigger_time = Column(DateTime, nullable=False, index=True)
    reminder_type = Column(String(32), default="general")
    related_id = Column(Integer, nullable=True)
    sent = Column(Boolean, default=False, index=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIFeedback(Base):
    """User feedback (thumbs up/down, comment) on an assistant message."""
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    rating = Column(String(16), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIUserPreference(Base):
    """Learned user preferences stored by the AI agent across conversations."""
    __tablename__ = "ai_user_preferences"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    key = Column(String(128), nullable=False)
    value = Column(Text, nullable=False)
    confidence = Column(String(8), default="medium")
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIGoal(Base):
    """Multi-turn goals tracked by the AI agent."""
    __tablename__ = "ai_goals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    description = Column(Text, nullable=False)
    status = Column(String(16), default="done", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class AIBroadcast(Base):
    """A personalized notification drafted by the AI for a specific user."""
    __tablename__ = "ai_broadcasts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    food_resource_id = Column(Integer, ForeignKey("food_resources.id"), nullable=True, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    channel = Column(String(16), default="sms")
    language = Column(String(8), default="en")
    message = Column(Text, nullable=False)
    status = Column(String(16), default="pending", index=True)
    batch_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

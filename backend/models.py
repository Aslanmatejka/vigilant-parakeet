"""
SQLAlchemy ORM models for the DoGoods backend.

Connects to Supabase PostgreSQL via DATABASE_URL.
Falls back to SQLite for local development when DATABASE_URL is not set.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DONOR = "donor"
    RECIPIENT = "recipient"
    ORGANIZER = "organizer"


class FoodCategory(str, enum.Enum):
    PRODUCE = "produce"
    DAIRY = "dairy"
    MEAT = "meat"
    SEAFOOD = "seafood"
    BAKERY = "bakery"
    CANNED = "canned"
    FROZEN = "frozen"
    PREPARED = "prepared"
    SNACKS = "snacks"
    BEVERAGES = "beverages"
    OTHER = "other"


class PerishabilityLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecurrenceFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReminderStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class FeedbackType(str, enum.Enum):
    BUG = "bug"
    FEATURE = "feature"
    GENERAL = "general"
    SAFETY = "safety"


class FeedbackStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ReportType(str, enum.Enum):
    FOOD_SAFETY = "food_safety"
    FRAUD = "fraud"
    HARASSMENT = "harassment"
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


class PickupReminderStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), default=UserRole.DONOR.value)
    phone = Column(String(32), nullable=True)
    address = Column(Text, nullable=True)
    coords_lat = Column(Float, nullable=True)
    coords_lng = Column(Float, nullable=True)

    # Trust / verification
    trust_score = Column(Integer, default=50)
    verified_by_aglf = Column(Boolean, default=False)
    school_partner = Column(Boolean, default=False)
    partner_badge = Column(String(64), nullable=True)
    partner_since = Column(DateTime, nullable=True)
    positive_feedback = Column(Integer, default=0)
    completed_exchanges = Column(Integer, default=0)
    verified_pickups = Column(Integer, default=0)

    # Contact verification
    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)

    # Preferences / profile
    household_size = Column(Integer, nullable=True)
    dietary_restrictions = Column(Text, nullable=True)   # JSON list
    allergies = Column(Text, nullable=True)              # JSON list
    preferred_categories = Column(Text, nullable=True)  # JSON list
    special_needs = Column(Text, nullable=True)
    notification_preferences = Column(Text, nullable=True)  # JSON
    notification_behavior = Column(String(32), nullable=True)

    # SMS consent
    sms_consent_given = Column(Boolean, default=False)
    sms_consent_date = Column(DateTime, nullable=True)
    sms_consent_ip = Column(String(64), nullable=True)
    sms_opt_out_date = Column(DateTime, nullable=True)
    sms_notification_types = Column(Text, nullable=True)  # JSON list

    # Referral
    referral_code = Column(String(16), unique=True, nullable=True)
    referred_by_code = Column(String(16), nullable=True)

    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    listings = relationship("FoodResource", back_populates="donor", foreign_keys="FoodResource.donor_id")


class FoodResource(Base):
    __tablename__ = "food_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    donor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(32), nullable=True)        # FoodCategory value
    qty = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    perishability = Column(String(16), nullable=True)   # PerishabilityLevel value
    est_weight_kg = Column(Float, nullable=True)

    expiration_date = Column(DateTime, nullable=True)
    date_label_type = Column(String(32), nullable=True)
    pickup_window_start = Column(DateTime, nullable=True)
    pickup_window_end = Column(DateTime, nullable=True)

    address = Column(Text, nullable=True)
    coords_lat = Column(Float, nullable=True)
    coords_lng = Column(Float, nullable=True)

    images = Column(Text, nullable=True)  # JSON list of URLs

    status = Column(String(32), default="available", index=True)
    available = Column(Boolean, default=True)
    claimed_at = Column(DateTime, nullable=True)
    urgency_score = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    donor = relationship("User", back_populates="listings", foreign_keys=[donor_id])


class DistributionCenter(Base):
    __tablename__ = "distribution_centers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    coords_lat = Column(Float, nullable=True)
    coords_lng = Column(Float, nullable=True)
    phone = Column(String(32), nullable=True)
    hours = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    verified_by_aglf = Column(Boolean, default=False)
    school_partner = Column(Boolean, default=False)
    partner_badge = Column(String(64), nullable=True)
    partner_since = Column(DateTime, nullable=True)

    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    inventory = relationship("CenterInventory", back_populates="center")


class CenterInventory(Base):
    __tablename__ = "center_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    center_id = Column(Integer, ForeignKey("distribution_centers.id"), nullable=False, index=True)

    item_name = Column(String(255), nullable=False)
    category = Column(String(32), nullable=True)
    quantity = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    is_available = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    center = relationship("DistributionCenter", back_populates="inventory")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(64), nullable=False, index=True)
    content = Column(Text, nullable=False)
    is_from_admin = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DonationSchedule(Base):
    __tablename__ = "donation_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(32), nullable=True)
    estimated_quantity = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    perishability = Column(String(16), nullable=True)

    frequency = Column(String(16), nullable=True)           # RecurrenceFrequency value
    day_of_week = Column(Integer, nullable=True)            # 0=Mon … 6=Sun
    day_of_month = Column(Integer, nullable=True)
    time_of_day = Column(String(8), nullable=True)          # HH:MM
    custom_interval_days = Column(Integer, nullable=True)

    next_donation_date = Column(DateTime, nullable=True)
    last_donation_date = Column(DateTime, nullable=True)

    send_reminders = Column(Boolean, default=True)
    reminder_hours_before = Column(Integer, default=24)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class DonationReminder(Base):
    __tablename__ = "donation_reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey("donation_schedules.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    donation_date = Column(DateTime, nullable=True)
    scheduled_for = Column(DateTime, nullable=False, index=True)

    status = Column(String(16), default=ReminderStatus.PENDING.value)
    email_sent = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    snooze_count = Column(Integer, default=0)
    snoozed_until = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    type = Column(String(32), default=FeedbackType.GENERAL.value)
    status = Column(String(32), default=FeedbackStatus.NEW.value)
    message = Column(Text, nullable=False)
    admin_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SafetyReport(Base):
    __tablename__ = "safety_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    listing_id = Column(Integer, ForeignKey("food_resources.id"), nullable=True)

    report_type = Column(String(32), default=ReportType.OTHER.value)
    status = Column(String(32), default=ReportStatus.PENDING.value)
    description = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)  # JSON list of URLs

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PickupReminder(Base):
    __tablename__ = "pickup_reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    listing_id = Column(Integer, ForeignKey("food_resources.id"), nullable=True)

    scheduled_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(16), default=PickupReminderStatus.SCHEDULED.value)
    sms_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)

    snooze_count = Column(Integer, default=0)
    snoozed_until = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FavoriteLocation(Base):
    __tablename__ = "favorite_locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    donor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    center_id = Column(Integer, ForeignKey("distribution_centers.id"), nullable=True)

    name = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    coords_lat = Column(Float, nullable=True)
    coords_lng = Column(Float, nullable=True)
    location_type = Column(String(32), default="general")
    notes = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)       # JSON list

    notify_new_listings = Column(Boolean, default=False)
    notification_radius_km = Column(Float, default=5.0)
    is_active = Column(Boolean, default=True)

    visit_count = Column(Integer, default=0)
    last_visited = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

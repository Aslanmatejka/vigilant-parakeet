"""
Pydantic request / response schemas for the DoGoods API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# Auth / User
# ---------------------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: Optional[str] = "donor"
    referral_code: Optional[str] = None
    phone: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


# ---------------------------------------------------------------------------
# Food Resources
# ---------------------------------------------------------------------------

class FoodResourceResponse(BaseModel):
    id: int
    donor_id: Optional[int] = None
    recipient_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    qty: Optional[float] = None
    unit: Optional[str] = None
    perishability: Optional[str] = None
    expiration_date: Optional[datetime] = None
    date_label_type: Optional[str] = None
    address: Optional[str] = None
    coords_lat: Optional[float] = None
    coords_lng: Optional[float] = None
    pickup_window_start: Optional[datetime] = None
    pickup_window_end: Optional[datetime] = None
    status: Optional[str] = None
    claimed_at: Optional[datetime] = None
    urgency_score: Optional[int] = 0
    images: Optional[List[str]] = None
    available: Optional[bool] = True
    est_weight_kg: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    donor: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Distribution Centers
# ---------------------------------------------------------------------------

class DistributionCenterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    coords_lat: Optional[float] = None
    coords_lng: Optional[float] = None
    phone: Optional[str] = None
    hours: Optional[str] = None


class DistributionCenterResponse(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    coords_lat: Optional[float] = None
    coords_lng: Optional[float] = None
    phone: Optional[str] = None
    hours: Optional[str] = None
    is_active: Optional[bool] = True
    verified_by_aglf: Optional[bool] = False
    school_partner: Optional[bool] = False
    partner_badge: Optional[str] = None
    partner_since: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CenterInventoryResponse(BaseModel):
    id: int
    center_id: int
    item_name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None
    is_available: Optional[bool] = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DistributionCenterWithInventory(DistributionCenterResponse):
    inventory: List[CenterInventoryResponse] = []

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Stats ──────────────────────────────────────────────

class AdminStatsResponse(BaseModel):
    total_users: int
    total_scans: int
    total_revenue_kobo: int  # sum of all top-ups
    active_users_7d: int
    new_users_7d: int


# ── Users ──────────────────────────────────────────────

class AdminUserItem(BaseModel):
    id: str
    email: str | None
    name: str | None
    credits: int
    credits_naira: float
    scan_count: int
    has_topped_up: bool
    is_admin: bool
    created_at: str


class AdminUserListResponse(BaseModel):
    users: list[AdminUserItem]
    total: int
    page: int
    per_page: int


class AdminUserDetail(BaseModel):
    id: str
    email: str | None
    phone: str | None
    name: str | None
    avatar_url: str | None
    auth_provider: str | None
    age: int | None
    sex: str | None
    credits: int
    credits_naira: float
    has_topped_up: bool
    is_admin: bool
    created_at: str

    scans: list[AdminUserScanItem] = []
    transactions: list[AdminUserTransactionItem] = []


class AdminUserScanItem(BaseModel):
    id: str
    status: str
    input_type: str | None
    source: str | None
    created_at: str


class AdminUserTransactionItem(BaseModel):
    id: str
    amount: int
    amount_naira: float
    reason: str
    created_at: str


# Forward ref update
AdminUserDetail.model_rebuild()


class AdminUserUpdate(BaseModel):
    is_admin: bool | None = None
    credits_adjustment_kobo: int | None = None  # positive = add, negative = deduct


# ── Transactions ───────────────────────────────────────

class AdminTransactionItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None
    amount: int
    amount_naira: float
    reason: str
    category: str
    label: str
    scan_id: str | None
    created_at: str


class AdminTransactionListResponse(BaseModel):
    transactions: list[AdminTransactionItem]
    total: int
    page: int
    per_page: int


# ── Scans ──────────────────────────────────────────────

class AdminScanItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None
    status: str
    input_type: str | None
    source: str | None
    full_unlocked: bool
    created_at: str


class AdminScanListResponse(BaseModel):
    scans: list[AdminScanItem]
    total: int
    page: int
    per_page: int


# ── Promo Codes ────────────────────────────────────────

class PromoCodeCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    discount_kobo: int = Field(..., gt=0)
    max_uses: int = Field(default=0, ge=0)  # 0 = unlimited
    expires_at: str | None = None  # ISO datetime string


class PromoCodeUpdate(BaseModel):
    is_active: bool | None = None
    max_uses: int | None = None
    expires_at: str | None = None


class PromoCodeResponse(BaseModel):
    id: str
    code: str
    discount_kobo: int
    discount_naira: float
    max_uses: int
    current_uses: int
    is_active: bool
    created_by: str | None
    expires_at: str | None
    created_at: str


class PromoCodeListResponse(BaseModel):
    promo_codes: list[PromoCodeResponse]
    total: int

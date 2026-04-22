from __future__ import annotations

from pydantic import BaseModel, Field


# ── Stats ──────────────────────────────────────────────

class AdminStatsResponse(BaseModel):
    total_users: int
    total_scans: int
    total_skin_analyses: int
    total_revenue_kobo: int  # sum of all top-ups
    total_bonuses_kobo: int  # sum of all signup bonuses given out
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
    skin_analyses: list[AdminUserSkinAnalysisItem] = []
    transactions: list[AdminUserTransactionItem] = []


class AdminUserSkinAnalysisItem(BaseModel):
    id: str
    status: str
    severity: str | None
    condition_names: list[str]
    created_at: str


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


# ── Skin Analyses ─────────────────────────────────────

class AdminSkinAnalysisItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None
    status: str
    severity: str | None
    condition_names: list[str]
    created_at: str


class AdminSkinAnalysisListResponse(BaseModel):
    analyses: list[AdminSkinAnalysisItem]
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


# ── Tariffs ───────────────────────────────────────────

class TariffResponse(BaseModel):
    signup_bonus_kobo: int
    referral_bonus_kobo: int
    cost_per_chat_kobo: int
    cost_per_file_upload_kobo: int
    cost_per_transcription_kobo: int
    cost_per_scan_unlock_kobo: int
    cost_per_skin_analysis_kobo: int

    # Convenience naira values
    signup_bonus_naira: float = 0
    referral_bonus_naira: float = 0
    cost_per_chat_naira: float = 0
    cost_per_file_upload_naira: float = 0
    cost_per_transcription_naira: float = 0
    cost_per_scan_unlock_naira: float = 0
    cost_per_skin_analysis_naira: float = 0


class TariffUpdate(BaseModel):
    signup_bonus_kobo: int | None = None
    referral_bonus_kobo: int | None = None
    cost_per_chat_kobo: int | None = None
    cost_per_file_upload_kobo: int | None = None
    cost_per_transcription_kobo: int | None = None
    cost_per_scan_unlock_kobo: int | None = None
    cost_per_skin_analysis_kobo: int | None = None


# ── Notifications ────────────────────────────────────

class AdminNotificationItem(BaseModel):
    id: str
    type: str  # new_user, payment, scan_completed, skin_analysis
    title: str
    description: str
    created_at: str


class AdminNotificationsResponse(BaseModel):
    notifications: list[AdminNotificationItem]
    total: int


# ── Support Tickets ──────────────────────────────────

class AdminTicketItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None
    category: str
    type: str
    subject: str
    status: str
    priority: str
    rating: int | None
    created_at: str


class AdminTicketDetail(AdminTicketItem):
    body: str
    admin_response: str | None
    responded_by: str | None
    responded_at: str | None
    updated_at: str


class AdminTicketListResponse(BaseModel):
    tickets: list[AdminTicketItem]
    total: int
    page: int
    per_page: int


class AdminTicketUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    admin_response: str | None = None


# ── Packages & pricing ──────────────────────────────────

class AdminPackagePrice(BaseModel):
    currency: str
    amount_minor: int
    is_active: bool = True


class AdminPackage(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    credits_granted: int
    display_order: int = 0
    is_popular: bool = False
    is_active: bool = True
    prices: list[AdminPackagePrice] = []


class AdminPackageListResponse(BaseModel):
    packages: list[AdminPackage]


class AdminPackageCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    credits_granted: int = Field(..., ge=0)
    display_order: int = 0
    is_popular: bool = False
    is_active: bool = True


class AdminPackageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    credits_granted: int | None = Field(None, ge=0)
    display_order: int | None = None
    is_popular: bool | None = None
    is_active: bool | None = None


class AdminPriceUpsert(BaseModel):
    amount_minor: int = Field(..., ge=0)
    is_active: bool = True

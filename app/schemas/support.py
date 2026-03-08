from __future__ import annotations

from pydantic import BaseModel, Field


# ── FAQ ───────────────────────────────────────────────

class FAQItem(BaseModel):
    question: str
    answer: str
    category: str


class FAQResponse(BaseModel):
    faqs: list[FAQItem]


# ── Support Chat ──────────────────────────────────────

class SupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class SupportChatResponse(BaseModel):
    message: str


# ── Tickets ───────────────────────────────────────────

VALID_CATEGORIES = {"account", "billing", "scans", "skin_analysis", "technical", "other"}
VALID_TYPES = {"complaint", "feedback", "bug_report", "feature_request", "testimonial"}


class TicketCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=30)
    type: str = Field(default="feedback", max_length=30)
    subject: str = Field(..., min_length=5, max_length=255)
    body: str = Field(..., min_length=10, max_length=5000)


class TicketRating(BaseModel):
    rating: int = Field(..., ge=1, le=5)


class TicketItem(BaseModel):
    id: str
    category: str
    type: str
    subject: str
    status: str
    admin_response: str | None
    rating: int | None
    created_at: str
    updated_at: str


class TicketDetail(TicketItem):
    body: str
    responded_at: str | None


class UserTicketsResponse(BaseModel):
    tickets: list[TicketItem]
    total: int
    page: int
    per_page: int


# ── Testimonials ──────────────────────────────────────

class TestimonialItem(BaseModel):
    name: str
    rating: int
    excerpt: str
    category: str
    created_at: str

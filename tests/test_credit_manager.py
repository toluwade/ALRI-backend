"""Unit tests for credit manager logic (no DB required)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.credit_manager import COST_PER_FULL_SCAN_KOBO, INITIAL_BALANCE_KOBO


def test_constants():
    assert INITIAL_BALANCE_KOBO == 500_000
    assert COST_PER_FULL_SCAN_KOBO == 50_000


def _make_user(credits: int = INITIAL_BALANCE_KOBO):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.credits = credits
    return user


def _make_scan(user_id, credit_deducted: bool = False):
    scan = MagicMock()
    scan.id = uuid.uuid4()
    scan.user_id = user_id
    scan.credit_deducted = credit_deducted
    scan.full_unlocked = False
    return scan


@pytest.mark.asyncio
async def test_deduct_for_full_scan_charges_once():
    from app.services.credit_manager import CreditManager

    db = AsyncMock()
    cm = CreditManager(db)

    user = _make_user(credits=500_000)
    scan = _make_scan(user.id, credit_deducted=False)

    await cm.require_and_deduct_for_full_scan(user=user, scan=scan)

    assert user.credits == 500_000 - COST_PER_FULL_SCAN_KOBO
    assert scan.credit_deducted is True
    assert scan.full_unlocked is True


@pytest.mark.asyncio
async def test_deduct_skips_when_already_charged():
    from app.services.credit_manager import CreditManager

    db = AsyncMock()
    cm = CreditManager(db)

    user = _make_user(credits=500_000)
    scan = _make_scan(user.id, credit_deducted=True)

    await cm.require_and_deduct_for_full_scan(user=user, scan=scan)

    # No deduction
    assert user.credits == 500_000


@pytest.mark.asyncio
async def test_deduct_fails_insufficient_balance():
    from app.services.credit_manager import CreditManager
    from fastapi import HTTPException

    db = AsyncMock()
    cm = CreditManager(db)

    user = _make_user(credits=1_000)
    scan = _make_scan(user.id, credit_deducted=False)

    with pytest.raises(HTTPException) as exc_info:
        await cm.require_and_deduct_for_full_scan(user=user, scan=scan)

    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_deduct_fails_wrong_user():
    from app.services.credit_manager import CreditManager
    from fastapi import HTTPException

    db = AsyncMock()
    cm = CreditManager(db)

    user = _make_user(credits=500_000)
    scan = _make_scan(uuid.uuid4(), credit_deducted=False)  # different user

    with pytest.raises(HTTPException) as exc_info:
        await cm.require_and_deduct_for_full_scan(user=user, scan=scan)

    assert exc_info.value.status_code == 403

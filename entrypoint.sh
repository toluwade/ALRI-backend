#!/bin/sh
set -e

echo "[entrypoint] Running database migrations..."

# ------------------------------------------------------------------
# Pre-migration: ensure alembic_version is correct before upgrading.
#
# Handles 3 scenarios:
#   1. Fresh DB          → alembic upgrade head creates everything
#   2. DB created by     → detect existing schema, stamp the right
#      create_all           version so upgrade head only runs what's new
#   3. Normal alembic DB → upgrade head runs any pending migrations
# ------------------------------------------------------------------
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def ensure_alembic_state():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        # Does alembic_version table exist?
        has_alembic = (await conn.execute(text(
            \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version')\"
        ))).scalar()

        if not has_alembic:
            has_users = (await conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')\"
            ))).scalar()
            if not has_users:
                print('[entrypoint] Fresh DB — alembic will create everything')
                await engine.dispose()
                return
            # DB was created outside alembic — need to stamp
            print('[entrypoint] DB exists but no alembic_version — creating tracker')
            await conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
            await conn.execute(text(\"INSERT INTO alembic_version VALUES ('0001_init')\"))
            await conn.commit()

        # Now alembic_version exists. Check current version and schema
        # to make sure the version matches reality.
        current = (await conn.execute(text('SELECT version_num FROM alembic_version'))).scalar()
        print(f'[entrypoint] Current alembic version: {current}')

        if current == '0001_init':
            # Check if migrations 0002–0006 were already applied manually
            # by looking for columns/tables they create.
            has_topped_up = (await conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.columns \"
                \"WHERE table_name = 'users' AND column_name = 'has_topped_up')\"
            ))).scalar()

            has_notifications = (await conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.tables \"
                \"WHERE table_name = 'notifications')\"
            ))).scalar()

            has_weight = (await conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.columns \"
                \"WHERE table_name = 'users' AND column_name = 'weight_kg')\"
            ))).scalar()

            reason_width = (await conn.execute(text(
                \"SELECT character_maximum_length FROM information_schema.columns \"
                \"WHERE table_name = 'credit_transactions' AND column_name = 'reason'\"
            ))).scalar() or 0

            credits_default = (await conn.execute(text(
                \"SELECT column_default FROM information_schema.columns \"
                \"WHERE table_name = 'users' AND column_name = 'credits'\"
            ))).scalar()

            # Walk forward through migrations and stamp the highest applied one
            stamped = '0001_init'
            if has_topped_up:
                stamped = '0002_pricing_and_features'
            if has_topped_up and has_weight:
                stamped = '0003_add_weight_height'
            if has_topped_up and has_weight and has_notifications:
                stamped = '0004_add_notifications'
            if has_topped_up and has_weight and has_notifications and reason_width >= 150:
                stamped = '0005_widen_reason'
            if has_topped_up and has_weight and has_notifications and reason_width >= 150 and str(credits_default) == '0':
                stamped = '0006_fix_credits_default'

            if stamped != current:
                print(f'[entrypoint] Schema is ahead of alembic — stamping as {stamped}')
                await conn.execute(text(\"UPDATE alembic_version SET version_num = :v\"), {'v': stamped})
                await conn.commit()
            else:
                print(f'[entrypoint] Schema matches version {current}')

    await engine.dispose()

asyncio.run(ensure_alembic_state())
" || echo "[entrypoint] WARNING: pre-migration check failed, continuing anyway"

# Run any pending migrations
alembic upgrade head
echo "[entrypoint] Migrations complete."

echo "[entrypoint] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

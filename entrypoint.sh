#!/bin/sh
set -e

echo "[entrypoint] Running database migrations..."

# Stamp as 0001 if alembic_version table doesn't exist but users table does
# (means DB was created by create_all, not alembic)
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def check_and_stamp():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        # Check if alembic_version exists
        result = await conn.execute(text(
            \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version')\"
        ))
        has_alembic = result.scalar()
        
        if not has_alembic:
            # Check if users table exists (DB created by create_all)
            result = await conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')\"
            ))
            has_users = result.scalar()
            
            if has_users:
                print('[entrypoint] DB exists but no alembic_version — stamping as 0001_init')
                await conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
                await conn.execute(text(\"INSERT INTO alembic_version VALUES ('0001_init')\"))
                await conn.commit()
            else:
                print('[entrypoint] Fresh DB — alembic will create everything')
        else:
            print('[entrypoint] alembic_version exists — normal migration')
    await engine.dispose()

asyncio.run(check_and_stamp())
" || echo "[entrypoint] WARNING: stamp check failed, continuing anyway"

alembic upgrade head || echo "[entrypoint] WARNING: migrations may have partially failed"

echo "[entrypoint] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

#!/bin/sh
# Waits for PostgreSQL, applies migrations (API container only), optionally creates the first admin.
set -e

python - <<'PY'
import time, sys
from sqlalchemy import create_engine, text
from app.config import get_settings
url = get_settings().database_url
for attempt in range(60):
    try:
        with create_engine(url).connect() as c:
            c.execute(text("select 1"))
        break
    except Exception as exc:
        print(f"waiting for database ({exc.__class__.__name__})", flush=True)
        time.sleep(2)
else:
    sys.exit("database not reachable")
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

if [ -n "$BOOTSTRAP_ADMIN_EMAIL" ] && [ -n "$BOOTSTRAP_ADMIN_PASSWORD" ]; then
  python - <<'PY'
import os
from sqlalchemy import select
from app.db import SessionLocal
from app.models import AppUser
from app.security import hash_password
email = os.environ["BOOTSTRAP_ADMIN_EMAIL"]
if len(os.environ["BOOTSTRAP_ADMIN_PASSWORD"]) < 10:
    raise SystemExit("BOOTSTRAP_ADMIN_PASSWORD in .env must be at least 10 characters")
with SessionLocal() as db:
    if not db.scalar(select(AppUser).where(AppUser.email == email)):
        db.add(AppUser(email=email, display_name=os.environ.get("BOOTSTRAP_ADMIN_NAME", "Admin"), role="admin",
                       password_hash=hash_password(os.environ["BOOTSTRAP_ADMIN_PASSWORD"])))
        db.commit()
        print(f"created admin {email}")
PY
fi

exec "$@"

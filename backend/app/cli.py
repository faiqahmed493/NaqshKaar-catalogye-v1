"""Admin commands.

    python -m app.cli create-user --email you@example.com --name "Your Name" --role admin
    python -m app.cli create-api-key --name "colab-gpu" --scopes worker
    python -m app.cli seed            # (re)load categories and the engine registry
    python -m app.cli check           # database, storage and validator connectivity
"""
from __future__ import annotations

import argparse
import getpass
import shutil
import sys
from pathlib import Path

from sqlalchemy import select, text

from .config import get_settings
from .db import SessionLocal, engine
from .models import ApiKey, AppUser
from .security import generate_api_key, hash_password
from .storage import get_storage

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def create_user(args) -> None:
    password = args.password or getpass.getpass("Password (min 10 chars): ")
    with SessionLocal() as db:
        if db.scalar(select(AppUser).where(AppUser.email == args.email)):
            sys.exit(f"User {args.email} already exists")
        db.add(AppUser(email=args.email, display_name=args.name, role=args.role, password_hash=hash_password(password)))
        db.commit()
    print(f"Created {args.role} {args.email}")


def create_api_key(args) -> None:
    scopes = sorted({s.strip() for s in args.scopes.split(",") if s.strip()})
    bad = set(scopes) - {"ingest", "worker", "catalogue_read"}
    if bad:
        sys.exit(f"Unknown scope(s): {', '.join(bad)}")
    full, prefix, digest = generate_api_key()
    with SessionLocal() as db:
        db.add(ApiKey(name=args.name, prefix=prefix, key_hash=digest, scopes=scopes))
        db.commit()
    print("API key (shown once, store it safely):")
    print(full)


def seed(_args) -> None:
    sql = (SQL_DIR / "0003_seed_reference.sql").read_text()
    with engine.begin() as conn:
        cur = conn.connection.cursor()   # raw psycopg cursor: whole file in one simple-protocol call
        cur.execute(sql)
        cur.close()
    print("Seeded categories and engines")


def check(_args) -> None:
    s = get_settings()
    with engine.connect() as conn:
        version = conn.execute(text("select version()")).scalar()
        vec = conn.execute(text("select count(*) from pg_extension where extname = 'vector'")).scalar()
    print(f"database: ok ({version.split(',')[0]}); pgvector {'on' if vec else 'off'}")
    store = get_storage()
    store.put("healthcheck/ping.txt", b"ok", "text/plain")
    assert store.get("healthcheck/ping.txt") == b"ok"
    print(f"storage: ok ({s.storage_backend})")
    if s.gltf_validator_cmd:
        exe = s.gltf_validator_cmd.split()[0]
        print(f"gltf validator: {'found' if shutil.which(exe) else 'NOT FOUND'} ({s.gltf_validator_cmd})")
    try:
        import trimesh  # noqa: F401
        print("trimesh: ok")
    except ImportError:
        print("trimesh: MISSING (asset qualification will fail)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("create-user")
    u.add_argument("--email", required=True)
    u.add_argument("--name", required=True)
    u.add_argument("--role", default="curator", choices=["admin", "curator", "asset_reviewer", "viewer"])
    u.add_argument("--password", help="omit to be prompted")
    u.set_defaults(fn=create_user)
    k = sub.add_parser("create-api-key")
    k.add_argument("--name", required=True)
    k.add_argument("--scopes", required=True, help="comma list of ingest, worker, catalogue_read")
    k.set_defaults(fn=create_api_key)
    sub.add_parser("seed").set_defaults(fn=seed)
    sub.add_parser("check").set_defaults(fn=check)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

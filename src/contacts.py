"""Stores the contact details of users who used the ATS checker or the resume builder.

- Database is chosen by DATABASE_URL (platform environment variable).
  * Not set: a SQLite file at data/app.db (for local testing only).
  * Set to a PostgreSQL URL (Render gives "postgresql://..."): data goes to that database.
    The code changes the URL to use the psycopg driver automatically.
- One row per submission in the table user_contacts. The table is created
  automatically the first time data is saved. The database itself must already exist.
- Personal data is never written to the log file.
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.logger import logging

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_PREFIX = "sqlite:///"
DEFAULT_DATABASE_URL = SQLITE_PREFIX + os.path.join(PROJECT_DIR, "data", "app.db")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\s()\-]+$")


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    # Store UTC time without tzinfo, so it works the same on every database.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserContact(Base):
    __tablename__ = "user_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30), index=True)  # "ats_check" or "resume_builder"
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(254), index=True)
    github: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    linkedin: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


_session_factory: Optional[sessionmaker] = None


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL
    # Render gives "postgres://" or "postgresql://". SQLAlchemy needs the psycopg driver named.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        url = _database_url()
        if url.startswith(SQLITE_PREFIX):
            os.makedirs(os.path.dirname(url[len(SQLITE_PREFIX):]), exist_ok=True)
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=280)
        Base.metadata.create_all(engine)  # creates user_contacts if it does not exist
        _session_factory = sessionmaker(bind=engine)
        logging.info("Contact database is ready.")
    return _session_factory


def clean_contact(
    full_name: str,
    phone: str,
    email: str,
    github: str,
    linkedin: str,
    consent: Optional[str],
) -> dict:
    """Check and tidy the submitted values. Raises ValueError with a message for the user."""
    if not consent:
        raise ValueError("Please agree to the privacy notice before continuing.")

    name = (full_name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("Please enter your full name (up to 120 characters).")

    mail = (email or "").strip()
    if not mail or len(mail) > 254 or not EMAIL_RE.match(mail):
        raise ValueError("Please enter a valid email address.")

    number = (phone or "").strip()
    digits = re.sub(r"\D", "", number)
    if not PHONE_RE.match(number) or not 7 <= len(digits) <= 15:
        raise ValueError("Please enter a valid mobile number (7 to 15 digits).")

    git = (github or "").strip()
    if len(git) > 300:
        raise ValueError("GitHub link is too long.")

    link = (linkedin or "").strip()
    if len(link) > 300:
        raise ValueError("LinkedIn link is too long.")

    return {
        "full_name": name,
        "phone": number,
        "email": mail,
        "github": git or None,
        "linkedin": link or None,
    }


def save_contact(source: str, contact: dict) -> None:
    """Store one submission. Database errors are raised so the caller can decide what to do."""
    session_factory = _get_session_factory()
    with session_factory() as session:
        session.add(UserContact(source=source, **contact))
        session.commit()
    logging.info(f"Contact saved from {source}.")  # no personal data in the log
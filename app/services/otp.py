import random
from datetime import datetime, timedelta

from app import db
from app.models import VerificationCode


def generate_otp_code(length=6):
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def create_verification_code(organization_id, request_id, purpose, ttl_minutes=10):
    code = generate_otp_code()
    entry = VerificationCode(
        organization_id=organization_id,
        request_id=request_id,
        code=code,
        purpose=purpose,
        expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
        is_used=False,
    )
    db.session.add(entry)
    return entry


def verify_latest_code(organization_id, request_id, purpose, submitted_code):
    entry = (
        VerificationCode.query.filter_by(
            organization_id=organization_id,
            request_id=request_id,
            purpose=purpose,
            is_used=False,
        )
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if not entry:
        return False, "No OTP code found. Generate a new one."
    if entry.expires_at < datetime.utcnow():
        return False, "OTP code has expired. Generate a new one."
    if (submitted_code or "").strip() != entry.code:
        return False, "Invalid OTP code."
    entry.is_used = True
    return True, None

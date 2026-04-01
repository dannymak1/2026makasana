import os
import re
import uuid

import qrcode


def _normalize_slug(value):
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return normalized.strip("-")


def ensure_verification_slug(organization):
    if organization.verification_slug:
        return organization.verification_slug
    base_slug = _normalize_slug(organization.slug or organization.name) or "organization"
    organization.verification_slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
    return organization.verification_slug


def generate_org_qr_code(organization, static_folder, base_url):
    verification_slug = ensure_verification_slug(organization)
    qr_relative_dir = os.path.join("assets", "images", "verification-qr")
    qr_absolute_dir = os.path.join(static_folder, qr_relative_dir)
    os.makedirs(qr_absolute_dir, exist_ok=True)

    qr_filename = f"{verification_slug}.png"
    qr_relative_path = f"{qr_relative_dir.replace(os.sep, '/')}/{qr_filename}"
    qr_absolute_path = os.path.join(qr_absolute_dir, qr_filename)
    verify_url = f"{base_url.rstrip('/')}/verify/{verification_slug}"

    qr_image = qrcode.make(verify_url)
    qr_image.save(qr_absolute_path)
    organization.qr_code_path = qr_relative_path
    return qr_relative_path

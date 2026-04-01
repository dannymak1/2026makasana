import re
import uuid
from datetime import datetime

from flask import has_request_context, request

from flask_login import UserMixin
from sqlalchemy import event
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True, index=True)
    email = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    verification_slug = db.Column(db.String(150), nullable=True, unique=True, index=True)
    qr_code_path = db.Column(db.String(255), nullable=True)
    verification_views_count = db.Column(db.Integer, nullable=False, default=0)
    logo_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    users = db.relationship("User", backref="organization", lazy=True)
    documents = db.relationship("Document", backref="organization", lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True, index=True)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)  # admin | client
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def set_password(self, raw_password):
        valid, message = self.validate_password(raw_password)
        if not valid:
            raise ValueError(message)
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_client(self):
        return self.role in {"client", "owner", "member"}

    @property
    def full_name(self):
        parts = [self.first_name or "", self.last_name or ""]
        display_name = " ".join(part for part in parts if part).strip()
        return display_name or self.username

    @staticmethod
    def validate_password(password):
        value = password or ""
        if len(value) < 8:
            return False, "Password must be at least 8 characters."
        if not re.search(r"[A-Z]", value):
            return False, "Password must include at least one uppercase letter."
        if not re.search(r"[a-z]", value):
            return False, "Password must include at least one lowercase letter."
        if not re.search(r"[0-9]", value):
            return False, "Password must include at least one number."
        if not re.search(r"[^A-Za-z0-9]", value):
            return False, "Password must include at least one special character."
        return True, None


class DocumentCategory(db.Model):
    __tablename__ = "document_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True, index=True)
    expiry_days = db.Column(db.Integer, nullable=False)

    documents = db.relationship("Document", backref="category", lazy=True)


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("document_categories.id"), nullable=False, index=True
    )
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)


class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), nullable=False, unique=True, index=True)
    excerpt = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    published_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @classmethod
    def published_latest(cls):
        return cls.query.filter_by(is_published=True).order_by(cls.published_at.desc())


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=True, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    actor_name = db.Column(db.String(200), nullable=False)
    action_type = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(100), nullable=True, index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class DocumentRequest(db.Model):
    __tablename__ = "document_requests"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    requester_name = db.Column(db.String(150), nullable=False)
    requester_email = db.Column(db.String(150), nullable=False, index=True)
    requester_phone = db.Column(db.String(50), nullable=True)
    requester_company = db.Column(db.String(150), nullable=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )


class VerificationCode(db.Model):
    __tablename__ = "verification_codes"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    request_id = db.Column(
        db.Integer, db.ForeignKey("document_requests.id"), nullable=False, index=True
    )
    code = db.Column(db.String(20), nullable=False, index=True)
    purpose = db.Column(db.String(100), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_used = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class SiteSetting(db.Model):
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(150), nullable=False, default="Makasana Consultancy")
    site_tagline = db.Column(db.String(255), nullable=True)
    logo_path = db.Column(db.String(255), nullable=True)
    favicon_path = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class MailingListSubscriber(db.Model):
    __tablename__ = "mailing_list_subscribers"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False, unique=True, index=True)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(100), nullable=True, index=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=True, index=True
    )
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    organization = db.relationship("Organization", lazy=True)


def log_activity(
    action_type,
    description,
    user=None,
    organization=None,
    entity_type=None,
    entity_id=None,
):
    actor = user.full_name if user else "System"
    org_id = organization.id if organization else (user.organization_id if user else None)
    ip_address = request.remote_addr if has_request_context() else None
    entry = ActivityLog(
        organization_id=org_id,
        user_id=user.id if user else None,
        actor_name=actor,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        ip_address=ip_address,
    )
    db.session.add(entry)
    return entry


@event.listens_for(Organization, "before_insert")
def _set_verification_slug_before_insert(mapper, connection, target):
    if target.verification_slug:
        return
    base_slug = (target.slug or "org").strip("-")
    target.verification_slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"

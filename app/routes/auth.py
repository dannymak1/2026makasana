import re
import secrets
import uuid
from datetime import datetime, timedelta
import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from app import db
from app.models import Organization, User
from app.services.emailer import build_branded_email_html, send_email_with_attachments
from app.services.logo_generator import generate_organization_text_logo
from app.services.mailing_list import upsert_subscriber

auth_bp = Blueprint("auth", __name__)


def _new_csrf_token():
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return token


def _valid_csrf_token(submitted_token):
    expected = session.get("csrf_token")
    return bool(expected and submitted_token and secrets.compare_digest(expected, submitted_token))


def _slugify(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _generate_unique_org_slug(org_name):
    base = _slugify(org_name)
    if not base:
        base = f"org-{uuid.uuid4().hex[:8]}"
    candidate = base
    while Organization.query.filter_by(slug=candidate).first() is not None:
        candidate = f"{base}-{uuid.uuid4().hex[:6]}"
    return candidate


def _validate_registration(
    username, password, confirm_password, org_name, user_phone, organization_phone, organization_email
):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", username or ""):
        return "Please enter a valid email address."
    if organization_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", organization_email):
        return "Please enter a valid organization email address."

    is_valid_password, password_error = User.validate_password(password)
    if not is_valid_password:
        return password_error
    if password != confirm_password:
        return "Password and confirm password do not match."

    if not (org_name or "").strip() or len(org_name.strip()) > 100:
        return "Organization name is required."

    if not (user_phone or "").strip() or not re.fullmatch(r"[+0-9()\-\s]{7,50}", user_phone.strip()):
        return "Your phone number is required."

    if not (organization_phone or "").strip() or not re.fullmatch(r"[+0-9()\-\s]{7,50}", organization_phone.strip()):
        return "Organization phone is required."

    if User.query.filter_by(username=username).first():
        return "Email already exists."

    return None


def _generate_signup_otp():
    return f"{secrets.randbelow(1000000):06d}"


def _save_signup_logo(file_obj):
    if not file_obj or not file_obj.filename:
        return None, None

    allowed_extensions = {"png", "jpg", "jpeg", "webp", "svg"}
    filename = secure_filename(file_obj.filename or "")
    if "." not in filename:
        return None, "Invalid logo file."
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in allowed_extensions:
        return None, "Only PNG/JPG/JPEG/WEBP/SVG logos are allowed."

    file_obj.stream.seek(0, os.SEEK_END)
    file_size = file_obj.stream.tell()
    file_obj.stream.seek(0)
    if file_size > 3 * 1024 * 1024:
        return None, "Logo file is too large. Maximum size is 3MB."

    logos_dir = os.path.join(current_app.static_folder, "assets", "images", "client-logos")
    os.makedirs(logos_dir, exist_ok=True)
    final_name = f"signup-{uuid.uuid4().hex[:12]}-{filename}"
    destination = os.path.join(logos_dir, final_name)
    file_obj.save(destination)
    return f"assets/images/client-logos/{final_name}", None


def _send_signup_otp_email(target_email, otp_code):
    subject = "Makasana Consultancy Signup Verification Code"
    body = (
        "Thank you for signing up with Makasana Consultancy.\n\n"
        f"Your one-time verification code is: {otp_code}\n\n"
        "This code expires in 10 minutes."
    )
    html_body = build_branded_email_html(
        current_app.config,
        heading="Email Verification Required",
        intro_text="Use this one-time code to complete your Makasana Consultancy signup.",
        content_html=(
            "<p style='margin:0 0 10px 0;'>Your OTP code is:</p>"
            f"<div style='font-size:28px; letter-spacing:6px; font-weight:700; color:#0f2f2f; padding:14px 16px; border:1px dashed #9bb79f; border-radius:10px; display:inline-block; background:#f7fbf6;'>{otp_code}</div>"
            "<p style='margin:14px 0 0 0;'>This code expires in 10 minutes.</p>"
        ),
        footer_note="If you did not initiate this signup, you can ignore this email.",
    )
    return send_email_with_attachments(
        current_app.config,
        subject=subject,
        body=body,
        to_email=target_email,
        attachments=None,
        html_body=html_body,
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("dms.dashboard"))

    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        if not _valid_csrf_token(csrf_token):
            flash("Invalid form session. Please try again.", "error")
            return redirect(url_for("auth.login"))

        username = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("dms.dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("public/login.html", csrf_token=_new_csrf_token())


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("dms.dashboard"))

    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        if not _valid_csrf_token(csrf_token):
            flash("Invalid form session. Please try again.", "error")
            return redirect(url_for("auth.signup"))

        username = request.form.get("email", "").strip().lower()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        organization_name = request.form.get("organization_name", "").strip()
        organization_email = request.form.get("organization_email", "").strip().lower()
        organization_phone = request.form.get("organization_phone", "").strip()
        user_phone = request.form.get("user_phone", "").strip()
        logo_file = request.files.get("organization_logo")

        validation_error = _validate_registration(
            username=username,
            password=password,
            confirm_password=confirm_password,
            org_name=organization_name,
            user_phone=user_phone,
            organization_phone=organization_phone,
            organization_email=organization_email,
        )
        if validation_error:
            flash(validation_error, "error")
            return render_template(
                "public/signup.html",
                csrf_token=_new_csrf_token(),
            )

        uploaded_logo_path, logo_error = _save_signup_logo(logo_file)
        if logo_error:
            flash(logo_error, "error")
            return render_template(
                "public/signup.html",
                csrf_token=_new_csrf_token(),
            )

        otp_code = _generate_signup_otp()
        otp_expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        session["signup_pending"] = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "password_hash": generate_password_hash(password),
            "organization_name": organization_name,
            "organization_email": organization_email,
            "organization_phone": organization_phone,
            "user_phone": user_phone,
            "uploaded_logo_path": uploaded_logo_path,
            "otp_code": otp_code,
            "otp_expires_at": otp_expires_at,
            "otp_attempts": 0,
        }

        if not _send_signup_otp_email(username, otp_code):
            session.pop("signup_pending", None)
            flash("Could not send verification code email. Please try again.", "error")
            return render_template(
                "public/signup.html",
                csrf_token=_new_csrf_token(),
            )

        session["signup_otp_sent"] = True
        flash("We sent a verification code to your email. Enter it to complete signup.", "success")
        return redirect(url_for("auth.verify_signup_otp"))

    return render_template(
        "public/signup.html",
        csrf_token=_new_csrf_token(),
    )


@auth_bp.route("/signup/verify", methods=["GET", "POST"])
def verify_signup_otp():
    pending = session.get("signup_pending")
    if not pending:
        flash("Signup session expired. Please register again.", "error")
        return redirect(url_for("auth.signup"))

    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        if not _valid_csrf_token(csrf_token):
            flash("Invalid form session. Please try again.", "error")
            return redirect(url_for("auth.verify_signup_otp"))

        otp_input = request.form.get("otp", "").strip()
        if not re.fullmatch(r"\d{6}", otp_input):
            flash("Verification code must be a 6-digit number.", "error")
            return render_template("public/signup_verify.html", csrf_token=_new_csrf_token())

        pending["otp_attempts"] = int(pending.get("otp_attempts", 0)) + 1
        if pending["otp_attempts"] > 5:
            flash("Too many failed attempts. Please sign up again.", "error")
            session.pop("signup_pending", None)
            return redirect(url_for("auth.signup"))
        session["signup_pending"] = pending

        if otp_input != pending.get("otp_code"):
            flash("Invalid verification code.", "error")
            return render_template("public/signup_verify.html", csrf_token=_new_csrf_token())

        expires_raw = pending.get("otp_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else datetime.utcnow()
        if datetime.utcnow() > expires_at:
            flash("Verification code expired. Please sign up again.", "error")
            session.pop("signup_pending", None)
            return redirect(url_for("auth.signup"))

        username = pending.get("username", "").strip().lower()
        if User.query.filter_by(username=username).first():
            session.pop("signup_pending", None)
            flash("Email already exists.", "error")
            return redirect(url_for("auth.signup"))

        organization_name = (pending.get("organization_name") or "").strip()
        if Organization.query.filter_by(name=organization_name).first():
            session.pop("signup_pending", None)
            flash("Organization name already exists. Please use another name.", "error")
            return redirect(url_for("auth.signup"))

        new_slug = _generate_unique_org_slug(organization_name)
        organization = Organization(
            name=organization_name[:100],
            slug=new_slug,
            email=(pending.get("organization_email") or "")[:150] or None,
            phone=(pending.get("organization_phone") or "")[:50] or None,
        )
        db.session.add(organization)
        db.session.flush()

        if pending.get("uploaded_logo_path"):
            organization.logo_path = pending.get("uploaded_logo_path")
        if not organization.logo_path:
            logo_path = generate_organization_text_logo(
                static_folder=current_app.static_folder,
                organization_name=organization.name,
            )
            organization.logo_path = logo_path

        user = User(
            username=username,
            first_name=(pending.get("first_name") or "")[:100] or None,
            last_name=(pending.get("last_name") or "")[:100] or None,
            phone=(pending.get("user_phone") or "")[:50],
            role="owner",
            organization_id=organization.id,
        )
        user.password_hash = pending.get("password_hash")
        db.session.add(user)

        upsert_subscriber(
            email=username,
            first_name=pending.get("first_name", ""),
            last_name=pending.get("last_name", ""),
            source="user_signup",
            organization_id=organization.id,
        )
        db.session.commit()
        session.pop("signup_pending", None)
        session.pop("signup_otp_sent", None)
        flash("Account verified and created successfully. You can sign in now.", "success")
        return redirect(url_for("auth.login"))

    otp_sent_notice = bool(session.pop("signup_otp_sent", False))
    return render_template(
        "public/signup_verify.html",
        csrf_token=_new_csrf_token(),
        otp_sent_notice=otp_sent_notice,
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

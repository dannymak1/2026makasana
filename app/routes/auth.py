import re
import secrets
import uuid

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models import Organization, User
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
    username, password, confirm_password, org_name, user_phone, organization_phone
):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", username or ""):
        return "Please enter a valid email address."

    is_valid_password, password_error = User.validate_password(password)
    if not is_valid_password:
        return password_error
    if password != confirm_password:
        return "Password and confirm password do not match."

    if not (org_name or "").strip():
        return "Organization name is required."

    if not (user_phone or "").strip():
        return "Your phone number is required."

    if not (organization_phone or "").strip():
        return "Organization phone is required."

    if User.query.filter_by(username=username).first():
        return "Email already exists."

    return None


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

        validation_error = _validate_registration(
            username=username,
            password=password,
            confirm_password=confirm_password,
            org_name=organization_name,
            user_phone=user_phone,
            organization_phone=organization_phone,
        )
        if validation_error:
            flash(validation_error, "error")
            return render_template(
                "public/signup.html",
                csrf_token=_new_csrf_token(),
            )

        new_slug = _generate_unique_org_slug(organization_name)
        organization = Organization(
            name=organization_name[:100],
            slug=new_slug,
            email=organization_email[:150] or None,
            phone=organization_phone[:50] or None,
        )
        db.session.add(organization)
        db.session.flush()

        user = User(
            username=username,
            first_name=first_name[:100] or None,
            last_name=last_name[:100] or None,
            phone=user_phone[:50],
            role="owner",
            organization_id=organization.id,
        )
        try:
            user.set_password(password)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template(
                "public/signup.html",
                csrf_token=_new_csrf_token(),
            )
        db.session.add(user)
        upsert_subscriber(
            email=username,
            first_name=first_name,
            last_name=last_name,
            source="user_signup",
            organization_id=organization.id,
        )
        db.session.commit()
        flash("Account created successfully. You can sign in now.", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "public/signup.html",
        csrf_token=_new_csrf_token(),
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

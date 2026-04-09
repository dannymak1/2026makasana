from datetime import datetime
import re
import secrets
from html import escape

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import desc
from sqlalchemy.exc import OperationalError

from app import db
from app.models import BlogPost, Document, DocumentRequest, Organization, User, log_activity
from app.services.emailer import build_branded_email_html, send_email_with_attachments
from app.services.mailing_list import upsert_subscriber
from app.services.verification import generate_org_qr_code

public_bp = Blueprint("public", __name__)


def _new_public_csrf_token():
    token = secrets.token_urlsafe(32)
    from flask import session
    session["public_csrf_token"] = token
    return token


def _valid_public_csrf_token(submitted_token):
    from flask import session
    expected = session.get("public_csrf_token")
    return bool(expected and submitted_token and secrets.compare_digest(expected, submitted_token))


def _get_public_client_logos():
    orgs_with_logos = (
        Organization.query.filter(Organization.logo_path.isnot(None))
        .filter(Organization.logo_path != "")
        .order_by(Organization.name.asc())
        .all()
    )
    return [org.logo_path for org in orgs_with_logos]


@public_bp.route("/")
def home():
    now = datetime.utcnow()
    try:
        organization_count = Organization.query.count()
    except OperationalError:
        db.session.rollback()
        organization_count = 0
    stats = {
        "organization_count": organization_count,
        "client_user_count": User.query.filter(User.role.in_(["client", "owner", "member"])).count(),
        "document_count": Document.query.count(),
        "active_document_count": Document.query.filter(Document.expires_at >= now).count(),
    }
    client_logos = _get_public_client_logos()
    latest_posts = (
        BlogPost.query.filter_by(is_published=True)
        .order_by(desc(BlogPost.published_at))
        .limit(3)
        .all()
    )
    return render_template(
        "public/home.html",
        stats=stats,
        client_logos=client_logos,
        latest_posts=latest_posts,
    )


@public_bp.route("/services")
def services():
    return render_template("public/services.html")


@public_bp.route("/about")
def about():
    return render_template("public/about.html")


@public_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        if not _valid_public_csrf_token(csrf_token):
            flash("Invalid form session. Please refresh and try again.", "error")
            return redirect(url_for("public.contact", status="failed"))

        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        subscribe = request.form.get("subscribe") == "on"

        if (
            not first_name
            or not last_name
            or not email
            or not subject
            or not message
            or len(first_name) > 100
            or len(last_name) > 100
            or len(subject) > 160
            or len(message) > 4000
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            flash("Please fill in all required contact fields.", "error")
            return redirect(url_for("public.contact", status="failed"))

        full_name = f"{first_name} {last_name}".strip()
        mail_subject = f"Website Contact Form: {subject}"
        mail_body = (
            "A new contact form message was submitted.\n\n"
            f"Name: {full_name}\n"
            f"Email: {email}\n"
            f"Subject: {subject}\n"
            f"Subscribe to updates: {'Yes' if subscribe else 'No'}\n\n"
            "Message:\n"
            f"{message}\n"
        )
        mail_html = build_branded_email_html(
            current_app.config,
            heading="New Website Contact Message",
            intro_text="A new contact request has been submitted from makasanaconsultancy.com.",
            content_html=(
                "<p style='margin:0 0 8px 0;'><strong>Name:</strong> "
                f"{escape(full_name)}</p>"
                "<p style='margin:0 0 8px 0;'><strong>Email:</strong> "
                f"{escape(email)}</p>"
                "<p style='margin:0 0 8px 0;'><strong>Subject:</strong> "
                f"{escape(subject)}</p>"
                "<p style='margin:0 0 8px 0;'><strong>Subscribe to updates:</strong> "
                f"{'Yes' if subscribe else 'No'}</p>"
                "<p style='margin:16px 0 8px 0;'><strong>Message</strong></p>"
                f"<div style='padding:12px; border:1px solid #d7e4d8; border-radius:8px; background:#f8fbf8;'>{escape(message)}</div>"
            ),
            footer_note="Please respond directly to the sender email shown above.",
        )

        sent_ok = send_email_with_attachments(
            current_app.config,
            subject=mail_subject,
            body=mail_body,
            to_email="info@makasanaconsultancy.com",
            attachments=None,
            html_body=mail_html,
        )
        if not sent_ok:
            flash("Could not send your message right now. Please try again later.", "error")
            return redirect(url_for("public.contact", status="failed"))

        if subscribe:
            upsert_subscriber(
                email=email,
                first_name=first_name,
                last_name=last_name,
                source="contact_form",
                organization_id=None,
            )

        flash("Your message has been sent successfully.", "success")
        return redirect(url_for("public.contact", status="sent"))

    return render_template("public/contact.html", csrf_token=_new_public_csrf_token())


@public_bp.route("/blog")
def blog():
    posts = BlogPost.published_latest().all()
    return render_template("public/blog.html", posts=posts)


@public_bp.route("/blog/<slug>")
def blog_detail(slug):
    post = BlogPost.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template("public/blog_detail.html", post=post)


@public_bp.route("/verify/<slug>", methods=["GET", "POST"])
def verify_organization(slug):
    organization = Organization.query.filter_by(verification_slug=slug).first_or_404()
    if request.method == "POST":
        requester_name = request.form.get("requester_name", "").strip()
        requester_email = request.form.get("requester_email", "").strip().lower()
        requester_phone = request.form.get("requester_phone", "").strip()
        requester_company = request.form.get("requester_company", "").strip()
        message = request.form.get("message", "").strip()

        if not requester_name or not requester_email or not message:
            flash("Name, email, and message are required.", "error")
            return redirect(url_for("public.verify_organization", slug=slug))

        req = DocumentRequest(
            organization_id=organization.id,
            requester_name=requester_name[:150],
            requester_email=requester_email[:150],
            requester_phone=requester_phone[:50] or None,
            requester_company=requester_company[:150] or None,
            message=message,
            status="pending",
        )
        db.session.add(req)
        db.session.flush()
        name_parts = requester_name.split(" ", 1)
        upsert_subscriber(
            email=req.requester_email,
            first_name=name_parts[0] if name_parts else None,
            last_name=name_parts[1] if len(name_parts) > 1 else None,
            source="public_request",
            organization_id=organization.id,
        )
        log_activity(
            action_type="document_request_created",
            description=f"Public request submitted by {req.requester_email}.",
            organization=organization,
            entity_type="document_request",
            entity_id=req.id,
        )
        db.session.commit()
        flash("Document request submitted successfully.", "success")
        return redirect(url_for("public.verify_organization", slug=slug))

    if not organization.qr_code_path:
        generate_org_qr_code(
            organization=organization,
            static_folder=current_app.static_folder,
            base_url=request.url_root,
        )
    organization.verification_views_count = (organization.verification_views_count or 0) + 1
    log_activity(
        action_type="verification_page_viewed",
        description=f"Verification page viewed for {organization.name}.",
        organization=organization,
        entity_type="organization",
        entity_id=organization.id,
    )
    db.session.commit()

    now = datetime.utcnow()
    documents = (
        Document.query.filter_by(organization_id=organization.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return render_template(
        "public/verify.html",
        organization=organization,
        documents=documents,
        now=now,
    )

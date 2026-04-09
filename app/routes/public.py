from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import desc
from sqlalchemy.exc import OperationalError

from app import db
from app.models import BlogPost, Document, DocumentRequest, Organization, User, log_activity
from app.services.mailing_list import upsert_subscriber
from app.services.verification import generate_org_qr_code

public_bp = Blueprint("public", __name__)


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


@public_bp.route("/contact")
def contact():
    return render_template("public/contact.html")


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

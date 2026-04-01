import os
import re
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db, role_required
from app.models import (
    BlogPost,
    Document,
    DocumentCategory,
    DocumentRequest,
    MailingListSubscriber,
    Organization,
    SiteSetting,
    User,
    log_activity,
)
from app.services.emailer import send_email_with_attachments
from app.services.mailing_list import upsert_subscriber
from app.services.otp import create_verification_code, verify_latest_code
from app.services.verification import generate_org_qr_code

admin_bp = Blueprint("admin", __name__)


def slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def generate_unique_blog_slug(title, desired_slug=None, current_post_id=None):
    base = slugify(desired_slug or title or "")
    if not base:
        base = f"post-{uuid.uuid4().hex[:8]}"

    candidate = base
    while True:
        query = BlogPost.query.filter_by(slug=candidate)
        if current_post_id is not None:
            query = query.filter(BlogPost.id != current_post_id)
        if query.first() is None:
            return candidate
        candidate = f"{base}-{uuid.uuid4().hex[:6]}"


def validate_pdf(file_obj):
    if not file_obj or not file_obj.filename:
        return False
    return file_obj.filename.lower().endswith(".pdf")


def validate_logo(file_obj):
    if not file_obj or not file_obj.filename:
        return False
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    ext = os.path.splitext(file_obj.filename)[1].lower()
    return ext in allowed


def get_uploaded_client_logos():
    organizations = (
        Organization.query.filter(Organization.logo_path.isnot(None))
        .filter(Organization.logo_path != "")
        .order_by(Organization.name.asc())
        .all()
    )
    return organizations


@admin_bp.route("/")
@login_required
@role_required("admin")
def dashboard():
    organizations_count = Organization.query.count()
    users_count = User.query.count()
    documents_count = Document.query.count()
    categories_count = DocumentCategory.query.count()
    blogs_count = BlogPost.query.count()
    all_requests = DocumentRequest.query.order_by(DocumentRequest.created_at.desc()).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_documents = Document.query.order_by(Document.uploaded_at.desc()).limit(10).all()
    categories = DocumentCategory.query.order_by(DocumentCategory.name.asc()).all()
    stats = {
        "organizations": organizations_count,
        "users": users_count,
        "documents": documents_count,
        "categories": categories_count,
        "blogs": blogs_count,
        "requests_total": len(all_requests),
        "requests_pending": len([req for req in all_requests if req.status == "pending"]),
        "requests_sent": len([req for req in all_requests if req.status == "sent"]),
    }
    now = datetime.utcnow()
    return render_template(
        "admin/dashboard.html",
        categories=categories,
        users=recent_users,
        documents=recent_documents,
        requests=all_requests[:10],
        stats=stats,
        now=now,
    )


@admin_bp.route("/settings")
@login_required
@role_required("admin")
def settings():
    organizations = Organization.query.order_by(Organization.name.asc()).all()
    return render_template(
        "admin/settings.html",
        organizations=organizations,
    )


@admin_bp.route("/organizations/create", methods=["POST"])
@login_required
@role_required("admin")
def create_organization():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    if not name:
        flash("Organization name is required.", "error")
        return redirect(url_for("admin.settings"))
    if not phone:
        flash("Organization phone is required.", "error")
        return redirect(url_for("admin.settings"))

    slug = slugify(name)
    if not slug:
        flash("Organization slug could not be generated.", "error")
        return redirect(url_for("admin.settings"))

    if Organization.query.filter(
        (Organization.name == name) | (Organization.slug == slug)
    ).first():
        flash("Organization already exists.", "error")
        return redirect(url_for("admin.settings"))

    organization = Organization(name=name, slug=slug, phone=phone[:50])
    db.session.add(organization)
    db.session.flush()
    generate_org_qr_code(
        organization=organization,
        static_folder=current_app.static_folder,
        base_url=request.url_root,
    )
    db.session.commit()
    flash("Organization created successfully.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/categories/create", methods=["POST"])
@login_required
@role_required("admin")
def create_category():
    name = request.form.get("name", "").strip()
    expiry_days = request.form.get("expiry_days", "").strip()
    if not name or not expiry_days:
        flash("Category name and expiry days are required.", "error")
        return redirect(url_for("admin.settings"))

    if not expiry_days.isdigit() or int(expiry_days) <= 0:
        flash("Expiry days must be a positive number.", "error")
        return redirect(url_for("admin.settings"))

    slug = slugify(name)
    if DocumentCategory.query.filter(
        (DocumentCategory.name == name) | (DocumentCategory.slug == slug)
    ).first():
        flash("Category already exists.", "error")
        return redirect(url_for("admin.settings"))

    category = DocumentCategory(name=name, slug=slug, expiry_days=int(expiry_days))
    db.session.add(category)
    db.session.commit()
    flash("Category created successfully.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/documents/upload", methods=["POST"])
@login_required
@role_required("admin")
def upload_document():
    organization_id = request.form.get("organization_id")
    category_id = request.form.get("category_id")
    file_obj = request.files.get("document")

    organization = Organization.query.get(organization_id)
    category = DocumentCategory.query.get(category_id)
    if not organization or not category:
        flash("Valid organization and category are required.", "error")
        return redirect(url_for("admin.manage_documents"))

    if not validate_pdf(file_obj):
        flash("Only PDF files are allowed.", "error")
        return redirect(url_for("admin.manage_documents"))

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    generated_name = f"{category.slug}_{organization.slug}_{timestamp}.pdf"
    final_name = secure_filename(generated_name)
    destination = os.path.join(current_app.config["UPLOAD_FOLDER"], final_name)

    file_obj.save(destination)

    uploaded_at = datetime.utcnow()
    expires_at = uploaded_at + timedelta(days=category.expiry_days)
    document = Document(
        organization_id=organization.id,
        category_id=category.id,
        file_name=final_name,
        file_path=f"uploads/{final_name}",
        uploaded_at=uploaded_at,
        expires_at=expires_at,
    )
    db.session.add(document)
    db.session.commit()
    flash("Document uploaded successfully.", "success")
    return redirect(url_for("admin.manage_documents"))


@admin_bp.route("/users/create", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    username = request.form.get("email", "").strip().lower()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "").strip()
    organization_id = request.form.get("organization_id")

    if (
        not username
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", username)
        or not password
        or not phone
        or role not in {"admin", "client"}
    ):
        flash("Email, phone, password, and valid role are required.", "error")
        return redirect(url_for("admin.settings"))

    if User.query.filter_by(username=username).first():
        flash("Email already exists.", "error")
        return redirect(url_for("admin.settings"))

    org_id = None
    if role == "client":
        organization = Organization.query.get(organization_id)
        if not organization:
            flash("Client users must belong to an organization.", "error")
            return redirect(url_for("admin.settings"))
        org_id = organization.id

    user = User(
        username=username,
        first_name=first_name[:100] or None,
        last_name=last_name[:100] or None,
        phone=phone[:50],
        role=role,
        organization_id=org_id,
    )
    try:
        user.set_password(password)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.settings"))
    db.session.add(user)
    upsert_subscriber(
        email=username,
        first_name=first_name,
        last_name=last_name,
        source="admin_created_user",
        organization_id=org_id,
    )
    db.session.commit()
    flash("User created successfully.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/logos/upload", methods=["POST"])
@login_required
@role_required("admin")
def upload_logo():
    organization_id = request.form.get("organization_id")
    file_obj = request.files.get("logo")
    organization = Organization.query.get(organization_id)
    if not organization:
        flash("Please select a valid organization.", "error")
        return redirect(url_for("admin.settings"))

    if not validate_logo(file_obj):
        flash("Only PNG/JPG/JPEG/WEBP/SVG logos are allowed.", "error")
        return redirect(url_for("admin.settings"))

    logos_dir = os.path.join(current_app.static_folder, "assets", "images", "client-logos")
    os.makedirs(logos_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    original = secure_filename(file_obj.filename)
    final_name = f"client_{timestamp}_{original}"
    destination = os.path.join(logos_dir, final_name)
    file_obj.save(destination)
    organization.logo_path = f"assets/images/client-logos/{final_name}"
    db.session.commit()
    flash("Organization logo uploaded and linked successfully.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/requests")
@login_required
@role_required("admin")
def requests_page():
    requests = DocumentRequest.query.order_by(DocumentRequest.created_at.desc()).all()
    stats = {
        "total": len(requests),
        "sent": len([r for r in requests if r.status == "sent"]),
        "pending": len([r for r in requests if r.status == "pending"]),
    }
    return render_template("admin/requests.html", requests=requests, stats=stats)


@admin_bp.route("/requests/<int:request_id>/send-documents", methods=["POST"])
@login_required
@role_required("admin")
def send_documents_request(request_id):
    doc_request = DocumentRequest.query.get_or_404(request_id)
    organization = Organization.query.get(doc_request.organization_id)
    owner = (
        User.query.filter_by(
            organization_id=doc_request.organization_id,
            role="owner",
        )
        .order_by(User.id.asc())
        .first()
    )
    if not owner:
        flash("No organization owner email found for OTP delivery.", "error")
        return redirect(url_for("admin.requests_page"))

    otp_entry = create_verification_code(
        organization_id=doc_request.organization_id,
        request_id=doc_request.id,
        purpose="send_documents",
    )
    log_activity(
        action_type="otp_generated",
        description=f"Generated OTP for request #{doc_request.id}.",
        user=current_user,
        organization=organization,
        entity_type="document_request",
        entity_id=doc_request.id,
    )
    send_email_with_attachments(
        config=current_app.config,
        subject=f"Makasana OTP for request #{doc_request.id}",
        body=(
            f"Your OTP code is {otp_entry.code}. "
            "It expires in 10 minutes."
        ),
        to_email=owner.username,
    )
    db.session.commit()
    flash("OTP generated and sent to organization owner email.", "success")
    return redirect(url_for("admin.requests_page"))


@admin_bp.route("/requests/<int:request_id>/verify-otp-send", methods=["POST"])
@login_required
@role_required("admin")
def verify_otp_and_send(request_id):
    doc_request = DocumentRequest.query.get_or_404(request_id)
    organization = Organization.query.get(doc_request.organization_id)
    submitted_otp = request.form.get("otp_code", "").strip()
    is_valid, message = verify_latest_code(
        organization_id=doc_request.organization_id,
        request_id=doc_request.id,
        purpose="send_documents",
        submitted_code=submitted_otp,
    )
    if not is_valid:
        flash(message, "error")
        return redirect(url_for("admin.requests_page"))

    log_activity(
        action_type="otp_verified",
        description=f"OTP verified for request #{doc_request.id}.",
        user=current_user,
        organization=organization,
        entity_type="document_request",
        entity_id=doc_request.id,
    )

    docs = (
        Document.query.filter_by(organization_id=doc_request.organization_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    attachments = [
        os.path.join(current_app.config["UPLOAD_FOLDER"], d.file_name)
        for d in docs
        if d.file_name
    ]
    sent_ok = send_email_with_attachments(
        config=current_app.config,
        subject=f"Makasana documents from {organization.name}",
        body=(
            "Hello,\n\nPlease find attached requested documents.\n\n"
            f"Request reference: #{doc_request.id}\n"
        ),
        to_email=doc_request.requester_email,
        attachments=attachments,
    )
    if not sent_ok:
        flash("Failed to send requester email. Check mail configuration.", "error")
        return redirect(url_for("admin.requests_page"))

    doc_request.status = "sent"
    doc_request.resolved_at = datetime.utcnow()
    doc_request.resolved_by_user_id = current_user.id
    log_activity(
        action_type="documents_sent",
        description=f"Sent documents for request #{doc_request.id}.",
        user=current_user,
        organization=organization,
        entity_type="document_request",
        entity_id=doc_request.id,
    )
    db.session.commit()
    flash("OTP verified and documents sent to requester.", "success")
    return redirect(url_for("admin.requests_page"))


@admin_bp.route("/requests/<int:request_id>/reject", methods=["POST"])
@login_required
@role_required("admin")
def reject_request(request_id):
    doc_request = DocumentRequest.query.get_or_404(request_id)
    organization = Organization.query.get(doc_request.organization_id)
    doc_request.status = "rejected"
    doc_request.resolved_at = datetime.utcnow()
    doc_request.resolved_by_user_id = current_user.id
    log_activity(
        action_type="document_request_rejected",
        description=f"Rejected request #{doc_request.id}.",
        user=current_user,
        organization=organization,
        entity_type="document_request",
        entity_id=doc_request.id,
    )
    db.session.commit()
    flash("Request rejected.", "success")
    return redirect(url_for("admin.requests_page"))


@admin_bp.route("/blogs")
@login_required
@role_required("admin")
def blogs_list():
    posts = BlogPost.query.order_by(BlogPost.published_at.desc()).all()
    return render_template("admin/blog_list.html", posts=posts)


@admin_bp.route("/blogs/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def create_blog():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        content = request.form.get("content", "").strip()
        image_path = request.form.get("image_path", "").strip()
        requested_slug = request.form.get("slug", "").strip()
        is_published = request.form.get("is_published") == "on"

        if not title or not category or not content:
            flash("Title, category, and content are required.", "error")
            return render_template("admin/blog_form.html", post=None)

        slug = generate_unique_blog_slug(title=title, desired_slug=requested_slug)
        post = BlogPost(
            title=title[:200],
            slug=slug,
            excerpt=excerpt or None,
            content=content,
            category=category[:100],
            image_path=image_path[:255] or None,
            is_published=is_published,
            published_at=datetime.utcnow(),
        )
        db.session.add(post)
        db.session.flush()
        log_activity(
            action_type="blog_created",
            description=f"Created blog post '{post.title}'.",
            user=current_user,
            entity_type="blog_post",
            entity_id=post.id,
        )
        db.session.commit()
        flash("Blog post created successfully.", "success")
        return redirect(url_for("admin.blogs_list"))

    return render_template("admin/blog_form.html", post=None)


@admin_bp.route("/blogs/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_blog(post_id):
    post = BlogPost.query.get_or_404(post_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        content = request.form.get("content", "").strip()
        image_path = request.form.get("image_path", "").strip()
        requested_slug = request.form.get("slug", "").strip()
        is_published = request.form.get("is_published") == "on"

        if not title or not category or not content:
            flash("Title, category, and content are required.", "error")
            return render_template("admin/blog_form.html", post=post)

        post.title = title[:200]
        post.slug = generate_unique_blog_slug(
            title=title, desired_slug=requested_slug, current_post_id=post.id
        )
        post.category = category[:100]
        post.excerpt = excerpt or None
        post.content = content
        post.image_path = image_path[:255] or None
        post.is_published = is_published
        if is_published and post.published_at is None:
            post.published_at = datetime.utcnow()

        log_activity(
            action_type="blog_updated",
            description=f"Updated blog post '{post.title}'.",
            user=current_user,
            entity_type="blog_post",
            entity_id=post.id,
        )
        db.session.commit()
        flash("Blog post updated successfully.", "success")
        return redirect(url_for("admin.blogs_list"))

    return render_template("admin/blog_form.html", post=post)


@admin_bp.route("/blogs/<int:post_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_blog(post_id):
    post = BlogPost.query.get_or_404(post_id)
    title = post.title
    db.session.delete(post)
    log_activity(
        action_type="blog_deleted",
        description=f"Deleted blog post '{title}'.",
        user=current_user,
        entity_type="blog_post",
        entity_id=post_id,
    )
    db.session.commit()
    flash("Blog post deleted successfully.", "success")
    return redirect(url_for("admin.blogs_list"))


@admin_bp.route("/users")
@login_required
@role_required("admin")
def users_page():
    search = request.args.get("q", "").strip().lower()
    query = User.query
    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%"))
            | (User.first_name.ilike(f"%{search}%"))
            | (User.last_name.ilike(f"%{search}%"))
            | (User.phone.ilike(f"%{search}%"))
        )
    users = query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users, search=search)


@admin_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@login_required
@role_required("admin")
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    phone = request.form.get("phone", "").strip()
    if not phone:
        flash("Phone number is required.", "error")
        return redirect(url_for("admin.users_page"))
    user.first_name = request.form.get("first_name", "").strip()[:100] or None
    user.last_name = request.form.get("last_name", "").strip()[:100] or None
    user.phone = phone[:50]
    db.session.commit()
    flash("User updated.", "success")
    return redirect(url_for("admin.users_page"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own admin user.", "error")
        return redirect(url_for("admin.users_page"))
    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for("admin.users_page"))


@admin_bp.route("/site-info", methods=["GET", "POST"])
@login_required
@role_required("admin")
def site_info():
    setting = SiteSetting.query.first()
    if setting is None:
        setting = SiteSetting(site_name="Makasana Consultancy")
        db.session.add(setting)
        db.session.commit()

    if request.method == "POST":
        setting.site_name = request.form.get("site_name", "").strip() or setting.site_name
        setting.site_tagline = request.form.get("site_tagline", "").strip() or None

        logo_file = request.files.get("logo")
        favicon_file = request.files.get("favicon")
        brand_dir = os.path.join(current_app.static_folder, "assets", "images", "branding")
        os.makedirs(brand_dir, exist_ok=True)

        if logo_file and logo_file.filename:
            logo_name = f"site_logo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(logo_file.filename)}"
            logo_file.save(os.path.join(brand_dir, logo_name))
            setting.logo_path = f"assets/images/branding/{logo_name}"
        if favicon_file and favicon_file.filename:
            favicon_name = f"site_favicon_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(favicon_file.filename)}"
            favicon_file.save(os.path.join(brand_dir, favicon_name))
            setting.favicon_path = f"assets/images/branding/{favicon_name}"

        db.session.commit()
        flash("Site info updated.", "success")
        return redirect(url_for("admin.site_info"))

    return render_template("admin/site_info.html", setting=setting)


@admin_bp.route("/mailing-list", methods=["GET", "POST"])
@login_required
@role_required("admin")
def mailing_list():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        source = request.form.get("source", "").strip()
        notes = request.form.get("notes", "").strip()
        subscriber = upsert_subscriber(
            email=email,
            first_name=first_name,
            last_name=last_name,
            source=source or "manual_admin_add",
            notes=notes or None,
        )
        if subscriber is None:
            flash("Email is required.", "error")
        else:
            flash("Subscriber saved.", "success")
        db.session.commit()
        return redirect(url_for("admin.mailing_list"))

    search = request.args.get("q", "").strip().lower()
    source_filter = request.args.get("source", "").strip().lower()
    query = MailingListSubscriber.query
    if search:
        query = query.filter(
            (MailingListSubscriber.email.ilike(f"%{search}%"))
            | (MailingListSubscriber.first_name.ilike(f"%{search}%"))
            | (MailingListSubscriber.last_name.ilike(f"%{search}%"))
        )
    if source_filter:
        query = query.filter(MailingListSubscriber.source == source_filter)
    subscribers = query.order_by(MailingListSubscriber.created_at.desc()).all()
    sources = [
        row[0]
        for row in db.session.query(MailingListSubscriber.source)
        .filter(MailingListSubscriber.source.isnot(None))
        .distinct()
        .all()
    ]
    return render_template(
        "admin/mailing_list.html",
        subscribers=subscribers,
        search=search,
        source_filter=source_filter,
        sources=sources,
    )


@admin_bp.route("/mailing-list/<int:subscriber_id>/edit", methods=["POST"])
@login_required
@role_required("admin")
def mailing_list_edit(subscriber_id):
    subscriber = MailingListSubscriber.query.get_or_404(subscriber_id)
    new_email = request.form.get("email", "").strip().lower()
    if not new_email:
        flash("Email is required.", "error")
        return redirect(url_for("admin.mailing_list"))
    existing = MailingListSubscriber.query.filter_by(email=new_email).first()
    if existing and existing.id != subscriber.id:
        flash("Email already exists.", "error")
        return redirect(url_for("admin.mailing_list"))
    subscriber.email = new_email
    subscriber.first_name = request.form.get("first_name", "").strip()[:100] or None
    subscriber.last_name = request.form.get("last_name", "").strip()[:100] or None
    subscriber.source = request.form.get("source", "").strip()[:100] or None
    subscriber.notes = request.form.get("notes", "").strip() or None
    subscriber.is_active = request.form.get("is_active") == "on"
    db.session.commit()
    flash("Subscriber updated.", "success")
    return redirect(url_for("admin.mailing_list"))


@admin_bp.route("/mailing-list/<int:subscriber_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def mailing_list_delete(subscriber_id):
    subscriber = MailingListSubscriber.query.get_or_404(subscriber_id)
    db.session.delete(subscriber)
    db.session.commit()
    flash("Subscriber deleted.", "success")
    return redirect(url_for("admin.mailing_list"))


@admin_bp.route("/mailing-list/<int:subscriber_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def mailing_list_toggle(subscriber_id):
    subscriber = MailingListSubscriber.query.get_or_404(subscriber_id)
    subscriber.is_active = not subscriber.is_active
    db.session.commit()
    flash("Subscriber status updated.", "success")
    return redirect(url_for("admin.mailing_list"))


@admin_bp.route("/manage-documents")
@login_required
@role_required("admin")
def manage_documents():
    documents = Document.query.order_by(Document.uploaded_at.desc()).all()
    organizations = Organization.query.order_by(Organization.name.asc()).all()
    categories = DocumentCategory.query.order_by(DocumentCategory.name.asc()).all()
    return render_template(
        "admin/manage_documents.html",
        documents=documents,
        organizations=organizations,
        categories=categories,
        now=datetime.utcnow(),
    )


@admin_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("admin")
def profile():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        if not phone:
            flash("Phone number is required.", "error")
            return redirect(url_for("admin.profile"))
        current_user.first_name = request.form.get("first_name", "").strip()[:100] or None
        current_user.last_name = request.form.get("last_name", "").strip()[:100] or None
        current_user.phone = phone[:50]
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if new_password:
            if new_password != confirm_password:
                flash("Passwords do not match.", "error")
                return redirect(url_for("admin.profile"))
            current_user.set_password(new_password)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("admin.profile"))
    return render_template("admin/profile.html")

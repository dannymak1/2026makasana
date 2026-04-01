import os
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db, role_required
from app.models import (
    ActivityLog,
    Document,
    DocumentCategory,
    DocumentRequest,
    Organization,
    User,
    log_activity,
)
from app.services.verification import generate_org_qr_code

dms_bp = Blueprint("dms", __name__)


def validate_pdf(file_obj):
    if not file_obj or not file_obj.filename:
        return False
    return file_obj.filename.lower().endswith(".pdf")


@dms_bp.route("/")
@login_required
@role_required("client", "owner", "member")
def home():
    return redirect(url_for("dms.dashboard"))


@dms_bp.route("/dashboard")
@login_required
@role_required("client", "owner", "member")
def dashboard():
    now = datetime.utcnow()
    org_id = current_user.organization_id
    if current_user.organization and not current_user.organization.qr_code_path:
        generate_org_qr_code(
            organization=current_user.organization,
            static_folder=current_app.static_folder,
            base_url=request.url_root,
        )
        db.session.commit()
    total_documents = Document.query.filter_by(organization_id=org_id).count()
    active_documents = Document.query.filter_by(organization_id=org_id).filter(
        Document.expires_at >= now
    )
    expiring_soon_documents = active_documents.filter(
        Document.expires_at <= now + timedelta(days=7)
    )
    expired_documents = Document.query.filter_by(organization_id=org_id).filter(
        Document.expires_at < now
    )
    recent_activity = (
        ActivityLog.query.filter_by(organization_id=org_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "dms/dashboard.html",
        total_documents=total_documents,
        active_documents=active_documents.count(),
        expiring_soon_documents=expiring_soon_documents.count(),
        expired_documents=expired_documents.count(),
        total_verification_views=current_user.organization.verification_views_count or 0,
        qr_code_path=current_user.organization.qr_code_path,
        verification_slug=current_user.organization.verification_slug,
        recent_activity=recent_activity,
    )


@dms_bp.route("/documents")
@login_required
@role_required("client", "owner", "member")
def documents():
    categories = DocumentCategory.query.order_by(DocumentCategory.name.asc()).all()
    documents = (
        Document.query.filter_by(organization_id=current_user.organization_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    now = datetime.utcnow()
    return render_template(
        "dms/documents.html",
        categories=categories,
        documents=documents,
        now=now,
    )


@dms_bp.route("/documents/upload", methods=["POST"])
@login_required
@role_required("client", "owner", "member")
def upload_document():
    category_id = request.form.get("category_id")
    file_obj = request.files.get("document")
    category = DocumentCategory.query.get(category_id)

    if not category:
        flash("Valid document category is required.", "error")
        return redirect(url_for("dms.documents"))

    if not validate_pdf(file_obj):
        flash("Only PDF files are allowed.", "error")
        return redirect(url_for("dms.documents"))

    organization = current_user.organization
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
    db.session.flush()
    log_activity(
        action_type="document_create",
        description=f"Uploaded document {final_name}.",
        user=current_user,
        organization=organization,
        entity_type="document",
        entity_id=document.id,
    )
    db.session.commit()
    flash("Document uploaded successfully.", "success")
    return redirect(url_for("dms.documents"))


@dms_bp.route("/documents/<int:document_id>/download")
@login_required
@role_required("client", "owner", "member")
def download_document(document_id):
    document = Document.query.get_or_404(document_id)
    if document.organization_id != current_user.organization_id:
        flash("You are not allowed to access this file.", "error")
        return redirect(url_for("dms.documents"))

    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        document.file_name,
        as_attachment=True,
    )


@dms_bp.route("/documents/<int:document_id>/update", methods=["POST"])
@login_required
@role_required("client", "owner", "member")
def update_document(document_id):
    document = Document.query.get_or_404(document_id)
    if document.organization_id != current_user.organization_id:
        flash("You are not allowed to edit this file.", "error")
        return redirect(url_for("dms.documents"))

    category_id = request.form.get("category_id")
    category = DocumentCategory.query.get(category_id)
    if not category:
        flash("Valid document category is required.", "error")
        return redirect(url_for("dms.documents"))

    old_name = document.file_name
    document.category_id = category.id
    document.expires_at = datetime.utcnow() + timedelta(days=category.expiry_days)

    file_obj = request.files.get("document")
    if file_obj and file_obj.filename:
        if not validate_pdf(file_obj):
            flash("Only PDF files are allowed.", "error")
            return redirect(url_for("dms.documents"))
        organization = current_user.organization
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        generated_name = f"{category.slug}_{organization.slug}_{timestamp}.pdf"
        final_name = secure_filename(generated_name)
        destination = os.path.join(current_app.config["UPLOAD_FOLDER"], final_name)
        file_obj.save(destination)
        document.file_name = final_name
        document.file_path = f"uploads/{final_name}"

    log_activity(
        action_type="document_update",
        description=f"Updated document {old_name}.",
        user=current_user,
        organization=current_user.organization,
        entity_type="document",
        entity_id=document.id,
    )
    db.session.commit()
    flash("Document updated successfully.", "success")
    return redirect(url_for("dms.documents"))


@dms_bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@login_required
@role_required("client", "owner", "member")
def delete_document(document_id):
    document = Document.query.get_or_404(document_id)
    if document.organization_id != current_user.organization_id:
        flash("You are not allowed to delete this file.", "error")
        return redirect(url_for("dms.documents"))

    file_name = document.file_name
    db.session.delete(document)
    log_activity(
        action_type="document_delete",
        description=f"Deleted document {file_name}.",
        user=current_user,
        organization=current_user.organization,
        entity_type="document",
        entity_id=document_id,
    )
    db.session.commit()
    flash("Document deleted successfully.", "success")
    return redirect(url_for("dms.documents"))


@dms_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("client", "owner", "member")
def profile():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not phone:
            flash("Phone number is required.", "error")
            return redirect(url_for("dms.profile"))

        current_user.first_name = first_name[:100] or None
        current_user.last_name = last_name[:100] or None
        current_user.phone = phone[:50]

        organization = current_user.organization
        if organization:
            org_name = request.form.get("organization_name", "").strip()
            org_email = request.form.get("organization_email", "").strip().lower()
            org_phone = request.form.get("organization_phone", "").strip()
            if not org_name:
                flash("Organization name is required.", "error")
                return redirect(url_for("dms.profile"))
            if not org_phone:
                flash("Organization phone is required.", "error")
                return redirect(url_for("dms.profile"))
            if org_name != organization.name:
                taken = Organization.query.filter_by(name=org_name).first()
                if taken and taken.id != organization.id:
                    flash("That organization name is already in use.", "error")
                    return redirect(url_for("dms.profile"))
            prev = (
                organization.name,
                organization.email or "",
                organization.phone or "",
            )
            organization.name = org_name[:100]
            organization.email = org_email[:150] or None
            organization.phone = org_phone[:50]
            new_tuple = (
                organization.name,
                organization.email or "",
                organization.phone or "",
            )
            if new_tuple != prev:
                log_activity(
                    action_type="organization_update",
                    description="Updated organization details from profile.",
                    user=current_user,
                    organization=organization,
                    entity_type="organization",
                    entity_id=organization.id,
                )

        if new_password:
            if new_password != confirm_password:
                flash("Password and confirm password do not match.", "error")
                return redirect(url_for("dms.profile"))
            is_valid_password, password_error = User.validate_password(new_password)
            if not is_valid_password:
                flash(password_error, "error")
                return redirect(url_for("dms.profile"))
            current_user.set_password(new_password)

        log_activity(
            action_type="profile_update",
            description="Updated user profile information.",
            user=current_user,
            organization=current_user.organization,
            entity_type="user",
            entity_id=current_user.id,
        )
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("dms.profile"))

    return render_template("dms/profile.html")


@dms_bp.route("/requests")
@login_required
@role_required("client", "owner", "member")
def requests_page():
    requests = (
        DocumentRequest.query.filter_by(organization_id=current_user.organization_id)
        .order_by(DocumentRequest.created_at.desc())
        .all()
    )
    stats = {
        "total": len(requests),
        "sent": len([r for r in requests if r.status == "sent"]),
        "pending": len([r for r in requests if r.status == "pending"]),
    }
    return render_template("dms/requests.html", requests=requests, stats=stats)

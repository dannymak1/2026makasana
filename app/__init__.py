import os
from datetime import date, datetime, timedelta
from functools import wraps

import click
from flask import Flask, abort
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from app.config import get_config_class

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _format_dt(value, fmt="%Y-%m-%d"):
    """Format datetimes for templates; handles str from DB drivers and datetime/date objects."""
    if value is None:
        return "-"
    if isinstance(value, (datetime, date)):
        return value.strftime(fmt)
    if isinstance(value, str):
        s = value.strip()
        if len(s) >= 10 and s[4] == "-":
            if any(x in fmt for x in ("%H", "%M", "%S", "%I")):
                normalized = s[:19].replace("T", " ", 1)
                for parse_fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        return datetime.strptime(normalized[:19], parse_fmt).strftime(fmt)
                    except ValueError:
                        continue
                return normalized[:16] if len(normalized) >= 16 else normalized
            return s[:10]
        return s
    return str(value)


def create_app(config_class=None):
    if config_class is None:
        config_class = get_config_class()
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.models import BlogPost, DocumentCategory, Organization, User
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.dms import dms_bp
    from app.routes.public import public_bp
    from app.services.verification import generate_org_qr_code

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.cli.command("seed-admin")
    @click.option("--username", default="admin@makasana.local", help="Admin email")
    @click.option("--password", default="admin123", help="Admin password")
    def seed_admin(username, password):
        existing = User.query.filter_by(username=username).first()
        if existing:
            click.echo("Admin user already exists.")
            return

        admin_user = User(username=username, role="admin", organization_id=None)
        try:
            admin_user.set_password(password)
        except ValueError as exc:
            click.echo(str(exc))
            return
        db.session.add(admin_user)
        db.session.commit()
        click.echo(f"Admin user created: {username}")

    @app.cli.command("seed-blogs")
    def seed_blogs():
        sample_posts = [
            {
                "title": "How to Stay Audit-Ready Without the Stress",
                "slug": "how-to-stay-audit-ready-without-the-stress",
                "category": "Compliance",
                "excerpt": "Learn how structured document management helps organizations stay compliant, organized, and ready for audits at any time.",
                "content": "Staying audit-ready does not have to feel overwhelming. With a structured document management process, organizations can keep compliance records in order, reduce last-minute panic, and improve visibility across critical requirements. A centralized system makes it easier to retrieve documents, monitor validity periods, and maintain confidence during reviews, inspections, and audits.",
                "image_path": "assets/images/blogImg1.png",
            },
            {
                "title": "Why Centralizing Your Documents Changes Everything",
                "slug": "why-centralizing-your-documents-changes-everything",
                "category": "Document Management",
                "excerpt": "Discover how moving from scattered files to a centralized system improves efficiency, visibility, and control.",
                "content": "When business records are scattered across emails, desktops, and shared folders, simple tasks become harder than they should be. Centralizing documents improves access, strengthens accountability, and gives teams one trusted source of truth. It also helps leaders track expiries, maintain consistency, and simplify day-to-day operations.",
                "image_path": "assets/images/blogImg2.png",
            },
            {
                "title": "Avoiding Common Compliance Mistakes",
                "slug": "avoiding-common-compliance-mistakes",
                "category": "Operations",
                "excerpt": "Understand the most common compliance pitfalls and how a proper system helps you avoid penalties and missed deadlines.",
                "content": "Many compliance failures come from preventable issues such as missed renewals, incomplete records, and weak document visibility. A structured platform reduces these risks by making responsibilities clearer and keeping key records easy to access. The goal is not only compliance, but confidence in daily operations.",
                "image_path": "assets/images/blogImg3.png",
            },
            {
                "title": "Building a Stronger Foundation for Regulatory Readiness",
                "slug": "building-a-stronger-foundation-for-regulatory-readiness",
                "category": "Regulatory",
                "excerpt": "A strong compliance foundation begins with better structure, clearer records, and consistent follow-through.",
                "content": "Regulatory readiness is built over time through disciplined record keeping, clear internal processes, and visibility into what matters most. Organizations that take documentation seriously are better prepared for audits, applications, reviews, and growth opportunities. A reliable system turns compliance from a burden into an operational advantage.",
                "image_path": "assets/images/blogImg1.png",
            },
        ]

        inserted_count = 0
        skipped_count = 0
        base_time = datetime.utcnow()

        for index, payload in enumerate(sample_posts):
            existing = BlogPost.query.filter_by(slug=payload["slug"]).first()
            if existing:
                skipped_count += 1
                click.echo(f"Skipped (exists): {payload['slug']}")
                continue

            post = BlogPost(
                title=payload["title"],
                slug=payload["slug"],
                excerpt=payload["excerpt"],
                content=payload["content"],
                category=payload["category"],
                image_path=payload["image_path"],
                is_published=True,
                published_at=base_time - timedelta(days=index),
            )
            db.session.add(post)
            inserted_count += 1
            click.echo(f"Inserted: {payload['slug']}")

        if inserted_count:
            db.session.commit()
        else:
            db.session.rollback()

        click.echo(f"Done. Inserted: {inserted_count}, Skipped: {skipped_count}")

    @app.cli.command("seed-categories")
    def seed_categories():
        categories = [
            {"name": "Tax Compliance", "slug": "tax-compliance", "expiry_days": 365},
            {"name": "Business Registration", "slug": "business-registration", "expiry_days": 9999},
            {"name": "Licenses & Permits", "slug": "licenses-permits", "expiry_days": 365},
            {"name": "Contracts & Agreements", "slug": "contracts-agreements", "expiry_days": 9999},
            {"name": "Insurance Documents", "slug": "insurance-documents", "expiry_days": 365},
            {"name": "Regulatory Filings", "slug": "regulatory-filings", "expiry_days": 180},
            {"name": "Audit Documents", "slug": "audit-documents", "expiry_days": 365},
            {"name": "HR & Employee Records", "slug": "hr-employee-records", "expiry_days": 9999},
        ]

        inserted_count = 0
        skipped_count = 0

        for payload in categories:
            existing = DocumentCategory.query.filter_by(slug=payload["slug"]).first()
            if existing:
                skipped_count += 1
                continue

            category = DocumentCategory(
                name=payload["name"],
                slug=payload["slug"],
                expiry_days=payload["expiry_days"],
            )
            db.session.add(category)
            inserted_count += 1

        if inserted_count:
            db.session.commit()
        else:
            db.session.rollback()

        click.echo(f"Inserted: {inserted_count}")
        click.echo(f"Skipped: {skipped_count}")

    @app.cli.command("generate-verification-qr")
    def generate_verification_qr():
        organizations = Organization.query.order_by(Organization.name.asc()).all()
        for organization in organizations:
            generate_org_qr_code(
                organization=organization,
                static_folder=app.static_folder,
                base_url=app.config.get("SITE_URL", "http://127.0.0.1:5000"),
            )
        db.session.commit()
        click.echo(f"Generated verification QR codes for {len(organizations)} organizations.")

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/bird_eye")
    app.register_blueprint(dms_bp, url_prefix="/dms")

    app.jinja_env.filters["format_dt"] = _format_dt

    return app

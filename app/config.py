import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Shared settings for all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 3,
        "max_overflow": 2,
        "pool_timeout": 30,
    }
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:5000")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "0") == "1"
    MAIL_HOST = os.environ.get("MAIL_HOST", "mail.makasanaconsultancy.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "465"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "no-reply@makasanaconsultancy.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "M@KAsana25")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "0") == "1"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "1") == "1"
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER", "no-reply@makasanaconsultancy.com"
    )


class DevelopmentConfig(Config):
    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://root:@localhost/makasana?charset=utf8mb4"
    )


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://mirazic1_makasana:20Makbuilt2026@localhost/"
        "mirazic1_makasana?charset=utf8mb4"
    )
    SITE_URL = os.environ.get("SITE_URL", "https://makasana.kolatech.co.ke")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "0") == "1"
    MAIL_HOST = os.environ.get("MAIL_HOST", "mail.makasanaconsultancy.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "465"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "no-reply@makasanaconsultancy.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "M@KAsana25")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "0") == "1"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "1") == "1"
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER", "no-reply@makasanaconsultancy.com"
    )


def get_config_class():
    name = (os.environ.get("FLASK_CONFIG") or "").strip().lower()
    if name == "production":
        return ProductionConfig
    if (os.environ.get("FLASK_ENV") or "").strip().lower() == "production":
        return ProductionConfig
    return DevelopmentConfig

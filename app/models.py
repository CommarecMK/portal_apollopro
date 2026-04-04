"""models.py — User model (sdílený s CRM DB) + oprávnění aplikací."""
from .extensions import db


class User(db.Model):
    __tablename__ = "user"
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    name          = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    is_active     = db.Column(db.Boolean, default=True)
    role          = db.Column(db.String(40), default="konzultant")


class PortalAppPermission(db.Model):
    """Která aplikace je přístupná pro kterého uživatele."""
    __tablename__ = "portal_app_permission"
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    app_key = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "app_key", name="uq_user_app"),)

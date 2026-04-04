"""routes/main.py — Portal: přihlášení + rozcestník."""
import os
from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from werkzeug.security import check_password_hash
from ..extensions import db
from ..sso import vytvor_token

bp = Blueprint("main", __name__)


# ── Sdílený User model (čte stejnou DB jako CRM) ──────────────────────
class User(db.Model):
    __tablename__ = "user"
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    name          = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    is_active     = db.Column(db.Boolean, default=True)
    role          = db.Column(db.String(40), default="konzultant")


# ── Seznam aplikací — přidávej sem nové dlaždice ──────────────────────
def sestav_aplikace(user):
    crm_url = os.environ.get("CRM_URL", "https://crm.apollopro.io")
    kb_url  = os.environ.get("KB_URL",  "https://kb.apollopro.io")

    token = vytvor_token(user.id, user.name, user.role)

    return [
        {
            "nazev": "CRM Superskladník",
            "popis": "Klienti, projekty, zápisy, nabídky",
            "ikona": "crm",
            "url": f"{crm_url}/auth?token={token}",
            "barva": "modra",
        },
        {
            "nazev": "Knowledge Base",
            "popis": "Znalostní databáze, dokumenty, AI analýzy",
            "ikona": "kb",
            "url": f"{kb_url}/auth?token={token}",
            "barva": "zelena",
        },
        # Sem přidej další appky v budoucnu:
        # {
        #     "nazev": "Nová appka",
        #     "popis": "Popis funkce",
        #     "ikona": "nova",
        #     "url": f"{nova_url}/auth?token={token}",
        #     "barva": "oranzova",
        # },
    ]


# ── ROUTES ─────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("main.portal"))
    return redirect(url_for("main.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.is_active and check_password_hash(user.password_hash, password):
            session["user_id"]   = user.id
            session["user_name"] = user.name
            session["user_role"] = user.role
            return redirect(url_for("main.portal"))
        error = "Nesprávný e-mail nebo heslo."
    return render_template("login.html", error=error)


@bp.route("/portal")
def portal():
    if "user_id" not in session:
        return redirect(url_for("main.login"))
    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("main.login"))
    aplikace = sestav_aplikace(user)
    return render_template("portal.html", aplikace=aplikace, current_user=user)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})

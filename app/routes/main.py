"""routes/main.py — Portal: přihlášení, rozcestník, admin."""
import os
from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, abort
from werkzeug.security import check_password_hash, generate_password_hash
from ..extensions import db
from ..sso import vytvor_token
from ..models import User, PortalAppPermission

bp = Blueprint("main", __name__)

# ── Definice všech dostupných aplikací ────────────────────────────────
ALL_APPS = [
    {
        "key": "crm",
        "nazev": "Zápisy (CRM)",
        "popis": "Klienti, projekty, zápisy, nabídky",
        "ikona": "crm",
        "barva": "#00AFF0",
        "url_env": "CRM_URL",
        "url_default": "https://crm.apollopro.io",
    },
    {
        "key": "brain",
        "nazev": "Brain",
        "popis": "Znalostní databáze, dokumenty, AI analýzy",
        "ikona": "brain",
        "barva": "#22c55e",
        "url_env": "KB_URL",
        "url_default": "https://brain.apollopro.io",
    },
    # Přidej sem další aplikace:
    # {
    #     "key": "nova",
    #     "nazev": "Nová aplikace",
    #     "popis": "Popis funkce",
    #     "ikona": "nova",
    #     "barva": "#f97316",
    #     "url_env": "NOVA_URL",
    #     "url_default": "https://nova.apollopro.io",
    # },
]


def get_user_apps(user):
    """Vrátí seznam aplikací které smí uživatel vidět."""
    if user.role == "superadmin":
        app_keys = [a["key"] for a in ALL_APPS]
    else:
        perms = PortalAppPermission.query.filter_by(user_id=user.id).all()
        app_keys = [p.app_key for p in perms]

    token = vytvor_token(user.id, user.name, user.role)
    result = []
    for app_def in ALL_APPS:
        if app_def["key"] not in app_keys:
            continue
        base_url = os.environ.get(app_def["url_env"], app_def["url_default"])
        result.append({
            **app_def,
            "url": f"{base_url}/auth?token={token}",
        })
    return result


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("main.login"))
        user = User.query.get(session["user_id"])
        if not user or user.role != "superadmin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


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
    aplikace = get_user_apps(user)
    je_admin = user.role == "superadmin"
    return render_template("portal.html", aplikace=aplikace, current_user=user, je_admin=je_admin)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


# ── ADMIN ──────────────────────────────────────────────────────────────

@bp.route("/admin")
@admin_required
def admin():
    uzivatele = User.query.order_by(User.name).all()
    vsechny_apps = ALL_APPS
    # Pro každého uživatele zjisti která oprávnění má
    perm_map = {}
    for p in PortalAppPermission.query.all():
        perm_map.setdefault(p.user_id, set()).add(p.app_key)
    return render_template("admin.html",
        uzivatele=uzivatele,
        vsechny_apps=vsechny_apps,
        perm_map=perm_map,
        current_user=User.query.get(session["user_id"])
    )


@bp.route("/admin/uzivatel/<int:user_id>/opravneni", methods=["POST"])
@admin_required
def uzivatel_opravneni(user_id):
    """Uloží oprávnění aplikací a roli pro uživatele."""
    user = User.query.get_or_404(user_id)
    vybrane_keys = request.form.getlist("app_keys")
    nova_role = request.form.get("role", user.role)

    # Ulož roli (superadmin nemůže měnit sám sobě roli)
    if user.id != session["user_id"]:
        user.role = nova_role
        user.is_admin = nova_role in ("admin", "superadmin")

    # Smaž stará oprávnění
    PortalAppPermission.query.filter_by(user_id=user_id).delete()

    # Ulož nová (superadmin má vše automaticky, checkboxy se ignorují)
    if nova_role != "superadmin":
        for key in vybrane_keys:
            if any(a["key"] == key for a in ALL_APPS):
                db.session.add(PortalAppPermission(user_id=user_id, app_key=key))

    db.session.commit()
    return redirect(url_for("main.admin"))


@bp.route("/admin/uzivatel/novy", methods=["POST"])
@admin_required
def novy_uzivatel():
    """Vytvoří nového uživatele."""
    email    = request.form.get("email", "").strip().lower()
    name     = request.form.get("name", "").strip()
    password = request.form.get("password", "").strip()
    role     = request.form.get("role", "konzultant")

    if not email or not name or not password:
        return redirect(url_for("main.admin"))

    if User.query.filter_by(email=email).first():
        return redirect(url_for("main.admin"))

    user = User(
        email=email,
        name=name,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=True,
        is_admin=(role == "superadmin"),
    )
    db.session.add(user)
    db.session.commit()
    return redirect(url_for("main.admin"))


@bp.route("/admin/uzivatel/<int:user_id>/aktivovat", methods=["POST"])
@admin_required
def uzivatel_aktivovat(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    return redirect(url_for("main.admin"))



@bp.route("/admin/uzivatel/<int:user_id>/heslo", methods=["POST"])
@admin_required
def uzivatel_heslo(user_id):
    """Nastaví nové heslo uživateli."""
    user = User.query.get_or_404(user_id)
    nove_heslo = request.form.get("heslo", "").strip()
    if len(nove_heslo) >= 6:
        user.password_hash = generate_password_hash(nove_heslo)
        db.session.commit()
    return redirect(url_for("main.admin"))


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})

# Apollo Pro — Systémová dokumentace pro Claude

> Tento soubor obsahuje kompletní popis všech aplikací, jejich kódu, databáze, deploymentu a konfigurace.
> Stačí ho nahrát do konverzace s Claudem a Claude bude mít veškerý kontext.
> Pro změny v konkrétních souborech Claude požádá o ten soubor — nemusíš nahrávat celé ZIPy.

---

## Přehled systému

Tři samostatné Flask aplikace na Railway, každá v samostatném GitHub repozitáři:

| Aplikace | Repozitář | Doména | Účel |
|---|---|---|---|
| **Portal** | `CommarecMK/apollopro-portal` | `apollopro.io` | Přihlášení + rozcestník s dlaždicemi |
| **CRM** | `CommarecMK/crm_superskladnik` | `crm.apollopro.io` | Klienti, projekty, zápisy, nabídky, Freelo |
| **Brain (KB)** | `CommarecMK/Commarec-KB` | `brain.apollopro.io` | Knowledge base, RAG dokumenty, AI analýzy |

Všechny tři jsou **Python/Flask + PostgreSQL**, deploy přes Railway (git push = automatický deploy).

---

## Architektura přihlášení (SSO)

```
1. Uživatel → apollopro.io → zadá email + heslo
2. Portal ověří heslo z CRM databáze (sdílená DB)
3. Portal vygeneruje SSO token (itsdangerous, platný 120s)
4. Klik na dlaždici → redirect na crm.apollopro.io/auth?token=XYZ
5. CRM/Brain ověří token → uloží user do vlastní session → pustí dovnitř
```

**Klíčová proměnná:** `SSO_SECRET` — musí být **stejná** na všech třech Railway službách.

---

## 1. PORTAL (`apollopro-portal`)

### Struktura souborů
```
apollopro-portal/
├── run.py
├── requirements.txt          # flask, flask-sqlalchemy, werkzeug, gunicorn, psycopg2-binary, itsdangerous
├── Procfile                  # gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
├── railway.toml
├── static/
│   └── logo-white.svg        # Commarec logo (bílé)
├── templates/
│   ├── login.html            # Přihlašovací stránka (styl CRM: tmavě modrá, Montserrat)
│   ├── portal.html           # Rozcestník s dlaždicemi (Apollo Pro + logo Commarec)
│   └── admin.html            # Správa uživatelů + přehled oprávnění
└── app/
    ├── __init__.py           # Flask factory, db.create_all()
    ├── extensions.py         # db = SQLAlchemy()
    ├── models.py             # User + PortalAppPermission
    ├── sso.py                # vytvor_token(), over_token()
    └── routes/
        └── main.py           # Všechny routes
```

### Kompletní zdrojové kódy

#### `app/models.py`
```python
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
    freelo_email   = db.Column(db.String(120), nullable=True)
    freelo_api_key = db.Column(db.String(200), nullable=True)

class PortalAppPermission(db.Model):
    __tablename__ = "portal_app_permission"
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    app_key = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "app_key", name="uq_user_app"),)
```

#### `app/sso.py`
```python
import os
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

SSO_SECRET = os.environ.get("SSO_SECRET", "ZMENTE-TOTO-NA-RAILWAY")
TOKEN_PLATNOST = 120  # sekund

def vytvor_token(user_id, user_name, user_role):
    s = URLSafeTimedSerializer(SSO_SECRET)
    return s.dumps({"id": user_id, "name": user_name, "role": user_role}, salt="sso-prechod")

def over_token(token):
    s = URLSafeTimedSerializer(SSO_SECRET)
    try:
        return s.loads(token, salt="sso-prechod", max_age=TOKEN_PLATNOST)
    except (SignatureExpired, BadSignature):
        return None
```

#### `app/routes/main.py` — klíčové části

**Definice aplikací** (přidání nové appky = přidej sem + nastav URL env var):
```python
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
]
```

**Routes:**
- `GET /` → redirect na portal nebo login
- `GET/POST /login` → přihlášení, čte z CRM DB
- `GET /portal` → rozcestník s dlaždicemi (vyžaduje session)
- `GET /logout` → smaže session
- `GET /admin` → správa uživatelů (vyžaduje role=superadmin)
- `POST /admin/uzivatel/<id>/opravneni` → uloží roli, heslo, Freelo, app přístupy
- `POST /admin/uzivatel/novy` → vytvoří uživatele
- `POST /admin/uzivatel/<id>/aktivovat` → toggle aktivní/neaktivní
- `POST /admin/uzivatel/<id>/heslo` → reset hesla
- `GET /health` → health check pro Railway

**Logika oprávnění aplikací:**
- `superadmin` → vidí všechny aplikace automaticky
- ostatní role → vidí jen co má v tabulce `portal_app_permission`

### Railway proměnné prostředí
| Proměnná | Hodnota |
|---|---|
| `DATABASE_URL` | `DATABASE_PUBLIC_URL` z CRM Postgres (veřejná URL!) |
| `SECRET_KEY` | silný náhodný řetězec (Flask session) |
| `SSO_SECRET` | **stejný** ve všech třech službách |
| `CRM_URL` | `https://crm.apollopro.io` |
| `KB_URL` | `https://brain.apollopro.io` |

---

## 2. CRM (`crm_superskladnik`)

### Struktura souborů
```
crm_superskladnik/
├── run.py
├── requirements.txt
├── Procfile
├── railway.toml
├── static/                   # logo-white.svg, logo-dark.svg, DrukCondensed font, JS
├── templates/                # 20+ šablon (login, dashboard, klienti, zápisy, nabídky...)
└── app/
    ├── __init__.py           # Flask factory + DB migrace
    ├── auth.py               # login_required, admin_required, role_required, can()
    ├── models.py             # User, Klient, KlientKontakt, Projekt, Zapis, Nabidka, ...
    ├── config.py             # TEMPLATE_SECTIONS, TEMPLATE_PROMPTS, TEMPLATE_NAMES
    ├── extensions.py         # db, ANTHROPIC_API_KEY, FREELO_API_KEY, ...
    ├── seed.py               # testovací data
    ├── sso.py                # vytvor_token(), over_token() — PŘIDÁNO
    └── routes/
        ├── main.py           # login, logout, portal, /auth (SSO vstup), dashboard, ...
        ├── admin.py          # šablony zápisů, klienti — BEZ správy uživatelů
        ├── klienti.py        # správa klientů a projektů
        ├── zapisy.py         # vytváření a editace zápisů
        ├── nabidky.py        # nabídky a položky
        ├── freelo.py         # Freelo integrace
        ├── report.py         # reporty
        └── portal.py         # klientský portál (role=klient)
```

### Klíčové změny oproti originálu
1. **Přidán `app/sso.py`** — generování a ověření SSO tokenů
2. **Přidána route `/auth`** v `routes/main.py` — SSO vstup z portálu
3. **Upraven login redirect** — po přihlášení jde na `/portal` (dlaždice) místo `/home`
4. **Přidána route `/portal`** v `routes/main.py` — záložní rozcestník přímo v CRM
5. **Přidán `portal_main.html`** template
6. **Admin (`routes/admin.py`) zjednodušen** — odstraněna správa uživatelů a přehled oprávnění, zůstaly jen šablony zápisů + klienti + Freelo diagnostika

### SSO vstup do CRM (`routes/main.py`)
```python
@bp.route("/auth")
def sso_vstup():
    from ..sso import over_token
    token = request.args.get("token", "")
    uzivatel = over_token(token)
    if not uzivatel:
        portal_url = os.environ.get("PORTAL_URL", "https://apollopro.io")
        return redirect(portal_url + "/login")
    user = User.query.get(uzivatel["id"])
    if not user or not user.is_active:
        portal_url = os.environ.get("PORTAL_URL", "https://apollopro.io")
        return redirect(portal_url + "/login")
    session["user_id"]   = user.id
    session["user_name"] = user.name
    session["is_admin"]  = user.is_admin
    session["user_role"] = user.role
    return redirect(url_for("main.home"))
```

### Role systém (auth.py)
```
superadmin → vše
admin      → edit_zapis_any, delete_zapis, manage_klient, freelo_setup, nabidky, nabidky_any, send_freelo, view_all, create_zapis, edit_zapis_own
konzultant → create_zapis, edit_zapis_own, send_freelo, view_all, manage_klient
obchodnik  → nabidky, nabidky_any, view_all, manage_klient
junior     → create_zapis, edit_zapis_own, view_assigned, manage_klient
klient     → portal_only
```

### DB modely (hlavní)
- `User` — uživatelé (email, name, password_hash, role, is_active, freelo_email, freelo_api_key, klient_id)
- `Klient` — klienti (nazev, slug, kontakt, email, ic, dic, sidlo, logo_url, profil_json, freelo_tasklist_id)
- `KlientKontakt` — kontaktní osoby klienta
- `Projekt` — projekty klientů (klient_id, user_id, datum_od, datum_do, freelo_project_id)
- `Zapis` — záznamy ze schůzek (template, title, transcript, output_json, tasks_json, klient_id, projekt_id, user_id, is_public, public_token)
- `Nabidka` — nabídky (cislo, nazev, klient_id, stav: draft/odeslana/prijata/zamitnuta)
- `NabidkaPolozka` — položky nabídky (cena, mnozstvi, dph_pct)
- `TemplateConfig` — editovatelné AI prompty pro šablony zápisů

### Railway proměnné prostředí
| Proměnná | Popis |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (interní Railway) |
| `SECRET_KEY` | Flask session key |
| `SSO_SECRET` | **stejný** ve všech třech službách |
| `PORTAL_URL` | `https://apollopro.io` |
| `KB_URL` | `https://brain.apollopro.io` |
| `ANTHROPIC_API_KEY` | pro AI funkce zápisů |
| `FREELO_API_KEY` | Freelo integrace |
| `FREELO_EMAIL` | Freelo email |
| `ADMIN_PASSWORD` | heslo prvního admina při inicializaci |

---

## 3. BRAIN / KB (`Commarec-KB`)

### Struktura souborů
```
Commarec-KB/
├── run.py
├── requirements.txt          # + pgvector, numpy, PyPDF2, python-docx, openpyxl, ...
├── Procfile
├── railway.toml
├── static/
│   ├── knowledge/            # PDF/TXT dokumenty pro indexaci
│   └── mascot/               # obrázky maskota
├── templates/
│   ├── index.html            # hlavní stránka (klienti, brain stats)
│   ├── klient.html           # detail klienta (dokumenty, analýzy, otázky)
│   ├── brain_historie.html   # learning log
│   ├── tipy.html             # tipy podle témat
│   └── analyza_pdf.html      # PDF export analýzy
└── app/
    ├── __init__.py           # Flask factory + pgvector + DB migrace
    ├── models.py             # Klient, Dokument, DokumentChunk, KlientAnalyza, ...
    ├── extensions.py         # db, API_SECRET
    ├── sso.py                # over_token(), prihlaseni_vyzadovano() — PŘIDÁNO
    └── routes/
        └── main.py           # všechny routes (PŘIDÁN /auth, @prihlaseni_vyzadovano)
    └── services/
        ├── ai.py             # AI analýzy, dotazy, brain generování
        ├── brain.py          # MAP-REDUCE brain aktualizace
        ├── embeddings.py     # pgvector embeddings, hledání
        └── extrakce.py       # extrakce textu z PDF/DOCX/XLSX/PPTX
```

### Klíčové změny oproti originálu
1. **Přidán `app/sso.py`** — ověření SSO tokenů + dekorátor `@prihlaseni_vyzadovano`
2. **Přidána route `/auth`** — SSO vstup z portálu (bez `@prihlaseni_vyzadovano`!)
3. **Všechny ostatní routes** mají `@prihlaseni_vyzadovano`
4. **API routes** (`/api/klient/...`, `/api/klienti`, `/api/health`) jsou bez SSO — chrání je `API_SECRET`

### SSO v KB (`app/sso.py`)
```python
import os
from functools import wraps
from flask import session, redirect
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

SSO_SECRET = os.environ.get("SSO_SECRET", "ZMENTE-TOTO-NA-RAILWAY")
TOKEN_PLATNOST = 120
CRM_LOGIN_URL = os.environ.get("PORTAL_URL", "https://apollopro.io") + "/login"

def over_token(token):
    s = URLSafeTimedSerializer(SSO_SECRET)
    try:
        return s.loads(token, salt="sso-prechod", max_age=TOKEN_PLATNOST)
    except (SignatureExpired, BadSignature):
        return None

def prihlaseni_vyzadovano(f):
    @wraps(f)
    def vnitrni(*args, **kwargs):
        if "user_id" not in session:
            return redirect(CRM_LOGIN_URL)
        return f(*args, **kwargs)
    return vnitrni
```

### DB modely
- `Klient` — klienti KB (nazev, slug, popis) — JINÉ než CRM klienti!
- `Dokument` — nahrané dokumenty (klient_id, nazev, typ, obsah_text, tagy, indexovano)
- `DokumentChunk` — chunky pro RAG (dokument_id, klient_id, text, embedding vector(1536))
- `KlientAnalyza` — uložené AI analýzy klientů (analyza_json)
- `KlientProfil` — profil klienta (profil_json)
- `CommarecBrain` — sdílený brain (brain_json, systemovy_prompt)
- `BrainOtazka` — otázky pro konzultanty (klient_id, otazka, odpoved, zodpovezeno)
- `BrainHistorie` — learning log (titulek, obsah, tagy, metriky_json, validovano)

### Railway proměnné prostředí
| Proměnná | Popis |
|---|---|
| `DATABASE_URL` | PostgreSQL URL s pgvector rozšířením |
| `SECRET_KEY` | Flask session key |
| `SSO_SECRET` | **stejný** ve všech třech službách |
| `PORTAL_URL` | `https://apollopro.io` |
| `ANTHROPIC_API_KEY` | AI analýzy a brain |
| `OPENAI_API_KEY` | embeddings (text-embedding-ada-002) |
| `API_SECRET` | pro API routes bez SSO |

---

## Databáze

### CRM databáze (PostgreSQL na Railway)
Používají ji: **CRM** (interní URL) + **Portal** (public URL)

Hlavní tabulky: `user`, `klient`, `klient_kontakt`, `projekt`, `zapis`, `nabidka`, `nabidka_polozka`, `template_config`, `user_presence`, `portal_app_permission` ← přidáno portálem

### KB databáze (PostgreSQL s pgvector na Railway)
Používá ji: pouze **Brain/KB**

Hlavní tabulky: `klient`, `dokument`, `dokument_chunk` (s vector(1536) sloupcem), `klient_analyza`, `klient_profil`, `commarec_brain`, `brain_otazka`, `brain_historie`

---

## Domény (Active24 DNS)

| Záznam | Typ | Cíl |
|---|---|---|
| `@` (apollopro.io) | ANAME | Railway portal URL |
| `_railway-verify` | TXT | railway-verify=... |
| `crm` | CNAME | Railway CRM URL |
| `_railway-verify.crm` | TXT | railway-verify=... |
| `brain` | CNAME | Railway KB URL |
| `_railway-verify.brain` | TXT | railway-verify=... |

---

## Design systém

Všechny tři aplikace sdílí stejný vizuální styl:
- **Font:** Montserrat (Google Fonts) — weights 400, 500, 600, 700, 900
- **Pozadí:** `#0E213E` (tmavě modrá)
- **Akcent:** `#00AFF0` (tyrkysová)
- **Pozadí karet:** `rgba(255,255,255,0.04-0.08)` s `rgba(255,255,255,0.07-0.12)` border
- **Border-radius:** 8-10px pro karty, 5-6px pro inputy/buttony
- **Orb efekt:** 2 rozmazané kruhy v rozích (filter: blur(80px))

---

## Jak přidat novou aplikaci

1. Vytvoř novou Flask appku s `app/sso.py` (zkopíruj z KB)
2. Přidej `@prihlaseni_vyzadovano` ke všem routes
3. Přidej route `/auth` (bez dekorátoru) — stejná logika jako v KB
4. Nastav `SSO_SECRET` a `PORTAL_URL` v Railway variables
5. V portálu (`app/routes/main.py`) přidej do `ALL_APPS`:
```python
{
    "key": "nova",
    "nazev": "Název aplikace",
    "popis": "Popis funkce",
    "ikona": "nova",       # přidej ikonu do portal.html template
    "barva": "#f97316",
    "url_env": "NOVA_URL",
    "url_default": "https://nova.apollopro.io",
}
```
6. Nastav `NOVA_URL` v Railway variables portálu

---

## Co Claude potřebuje pro různé typy úkolů

| Úkol | Co nahrát |
|---|---|
| Změna textu, stylu, designu | Jen tento CLAUDE.md |
| Přidání nové aplikace | Jen tento CLAUDE.md |
| Úprava admin logiky | Jen tento CLAUDE.md (zdrojáky portálu jsou zde) |
| Úprava CRM routes/logiky | Tento CLAUDE.md + konkrétní soubor z CRM |
| Úprava KB routes/logiky | Tento CLAUDE.md + konkrétní soubor z KB |
| Nová feature v CRM | Tento CLAUDE.md + relevantní CRM soubory |
| Řešení chyby | Tento CLAUDE.md + log chyby (screenshot nebo text) |

---

## Rychlý checklist nasazení

- [ ] `SSO_SECRET` stejný na všech třech Railway službách
- [ ] `SECRET_KEY` nastaveno na všech třech Railway službách
- [ ] `DATABASE_URL` portálu = `DATABASE_PUBLIC_URL` z CRM Postgres
- [ ] DNS záznamy na Active24 nastaveny a zelené v Railway
- [ ] HTTPS certifikáty aktivní (automaticky po ověření DNS)
- [ ] Ruční záloha DB před každým větším deployem (Railway → Postgres → Backups)

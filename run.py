"""
NEXUS SOC — Point d'entrée principal de l'API
==============================================
Monte tous les routers FastAPI et sert le frontend statique.

Démarrage :
    uvicorn run:app --host 0.0.0.0 --port 8000 --reload

Accès :
    API docs  : http://localhost:8000/docs
    Frontend  : http://localhost:8000/app/
    Login     : http://localhost:8000/app/login.html
    Console   : http://localhost:8000/app/console.html
    Portail   : http://localhost:8000/app/portail.html
"""
import os
import sys

# Rendre tous les Lots importables depuis la racine du projet
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# ─── Chargement du fichier .env (variables d'environnement centralisées) ────
# Doit s'exécuter AVANT tout import qui lit os.getenv(). On n'écrase pas les
# variables déjà définies dans l'environnement (ex. systemd, Docker, CI).
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path, override=False)
        print(f"[run] ✓ .env chargé depuis {_env_path}")
    else:
        print("[run] ⚠ aucun fichier .env trouvé — utilisation des valeurs par défaut")
except ImportError:
    print("[run] ⚠ python-dotenv non installé — pip install -r requirements.txt")

# ─── Application principale ──────────────────────────────────────────────────
# On importe l'app FastAPI depuis le scoring-service (Lot 1).
# Le nom du module utilise un underscore car Python n'autorise pas les tirets.
import importlib.util, types

def _load_module(alias, path):
    """Charge un fichier .py sous un alias sans modifier son code."""
    spec = importlib.util.spec_from_file_location(alias, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod

scoring_mod = _load_module(
    "nexus_scoring",
    os.path.join(PROJECT_ROOT, "Lot1_Agent_Go", "scoring-service_app.py"),
)
app = scoring_mod.app

# ─── CORS ────────────────────────────────────────────────────────────────────
# Origines autorisées configurables par variable d'environnement.
#   NEXUS_CORS_ORIGINS="https://soc.minfi.gov.cm,https://portail.minfi.cm"
# Par défaut (dev) : localhost uniquement. NE JAMAIS laisser "*" en production
# avec allow_credentials=True (interdit par la spec CORS et risque de sécurité).
from fastapi.middleware.cors import CORSMiddleware

_cors_env = os.getenv("NEXUS_CORS_ORIGINS", "").strip()
if _cors_env == "*":
    _origins, _allow_creds = ["*"], False  # crédentials interdits avec wildcard
elif _cors_env:
    _origins, _allow_creds = [o.strip() for o in _cors_env.split(",") if o.strip()], True
else:
    _origins = [
        "http://localhost:8000", "http://127.0.0.1:8000",
        "http://localhost:5500", "http://127.0.0.1:5500",  # live-server dev
    ]
    _allow_creds = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)
print(f"[run] CORS origins: {_origins} (credentials={_allow_creds})")

# ─── Headers de sécurité (HSTS + nosniff + frame-deny) ───────────────────────
# HSTS dit au navigateur : "à partir de maintenant, n'accepte que HTTPS pour ce
# domaine pendant 1 an, sous-domaines inclus". Active dès la 1ʳᵉ visite après
# déploiement. Couplé à "Always Use HTTPS" côté Cloudflare → "Pas sécurisé"
# disparaît même si l'utilisateur tape l'URL sans https://.
@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Strict-Transport-Security",
        "max-age=31536000; includeSubDomains; preload",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response

# ─── Routers supplémentaires ─────────────────────────────────────────────────
# Les dossiers des Lots sont ajoutés au PYTHONPATH pour que les imports croisés
# fonctionnent (ex. admin_api.py qui importe auth_middleware pour valider le JWT).
for _lot in ("Lot1_Agent_Go", "Lot7_Console_Fournisseur", "Lot8_PLG"):
    _p = os.path.join(PROJECT_ROOT, _lot)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _try_include(module_path, attrs, prefix_log):
    """Charge un module et monte un ou plusieurs routers (attrs = str | list)."""
    if isinstance(attrs, str):
        attrs = [attrs]
    try:
        mod_name = os.path.splitext(os.path.basename(module_path))[0]
        spec = importlib.util.spec_from_file_location(mod_name, module_path)
        mod  = importlib.util.module_from_spec(spec)
        # Enregistrer sous son vrai nom pour permettre les imports croisés
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        mounted = 0
        for attr in attrs:
            router = getattr(mod, attr, None)
            if router is not None:
                app.include_router(router)
                mounted += 1
        if mounted:
            print(f"[run] ✓ {prefix_log} monté ({mounted} routeur(s))")
        else:
            print(f"[run] ✗ {prefix_log} — aucun routeur trouvé parmi {attrs}")
    except Exception as e:
        print(f"[run] ✗ {prefix_log} ignoré — {e}")

# auth_middleware expose `auth_router` (et non `router`)
_try_include(
    os.path.join(PROJECT_ROOT, "Lot1_Agent_Go",              "auth_middleware.py"),
    "auth_router", "Auth /auth/*",
)
# admin_api expose TROIS routeurs : `router` (/admin), `analyst_router` (/analyst),
# `portail_router` (/portal — vue DSI filtrée par tenant JWT)
_try_include(
    os.path.join(PROJECT_ROOT, "Lot7_Console_Fournisseur",  "admin_api.py"),
    ["router", "analyst_router", "portail_router"],
    "Admin /admin/* + Analyste /analyst/* + Portail /portal/*",
)
_try_include(
    os.path.join(PROJECT_ROOT, "Lot7_Console_Fournisseur",  "provisioning_api.py"),
    "router", "Provisioning /provision/*",
)
_try_include(
    os.path.join(PROJECT_ROOT, "Lot8_PLG",                  "plg_api.py"),
    "router", "PLG /plg/*",
)

# ─── Frontend statique ───────────────────────────────────────────────────────
try:
    from fastapi.staticfiles import StaticFiles
    frontend_dir = os.path.join(PROJECT_ROOT, "Lot9_Frontend")
    if os.path.isdir(frontend_dir):
        app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")
        print("[run] ✓ Frontend monté sur /app")
    else:
        print("[run] ✗ Répertoire Lot9_Frontend introuvable")
except Exception as e:
    print(f"[run] ✗ Frontend ignoré — {e}")

# ─── Pool asyncpg pour le module PLG ──────────────────────────────────────────
# plg_api.py attend un pool asyncpg sur app.state.db (dépendance _db).
# On l'initialise au démarrage à partir du même DB_DSN que le reste de l'app.
@app.on_event("startup")
async def _init_plg_pool():
    dsn = os.getenv("DB_DSN")
    if not dsn:
        app.state.db = None
        print("[run] ✗ pool PLG : DB_DSN non défini")
        return
    try:
        import asyncpg
        app.state.db = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        print("[run] ✓ pool asyncpg PLG initialisé (app.state.db)")
    except Exception as e:
        app.state.db = None
        print(f"[run] ✗ pool asyncpg PLG indisponible — {e}")


@app.on_event("shutdown")
async def _close_plg_pool():
    pool = getattr(app.state, "db", None)
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass


# ─── Redirection racine → landing page (vitrine) ─────────────────────────────
# Le point d'entrée web est la landing (présentation du produit) ;
# le point d'entrée PWA (start_url dans manifest.json) reste login.html
# pour que l'app installée ouvre directement sur la connexion.
from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/landing.html")

print("[run] NEXUS SOC démarré")
print("[run]   Landing  : http://localhost:8000/app/landing.html")
print("[run]   Login    : http://localhost:8000/app/login.html  (PWA start_url)")
print("[run]   Docs     : http://localhost:8000/app/docs.html")
print("[run]   Contact  : http://localhost:8000/app/contact.html")

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
# Lot4_SOAR y figure depuis la phase 2 : admin_api importe « connecteurs »,
# qui transforme une décision approuvée en effet réel sur le pare-feu et
# l'annuaire.
for _lot in ("Lot1_Agent_Go", "Lot4_SOAR", "Lot7_Console_Fournisseur"):
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
# admin_api expose CINQ routeurs : `router` (/admin), `analyst_router` (/analyst),
# `portail_router` (/portal — vue DSI filtrée par tenant JWT),
# `monitor_router` (/monitor — dérive des modèles IA),
# `contact_router` (/contact — demandes internes de mise sous supervision)
_try_include(
    os.path.join(PROJECT_ROOT, "Lot7_Console_Fournisseur",  "admin_api.py"),
    ["router", "analyst_router", "portail_router", "monitor_router", "contact_router"],
    "Admin /admin/* + Analyste /analyst/* + Portail /portal/* + /monitor/* + /contact/*",
)
_try_include(
    os.path.join(PROJECT_ROOT, "Lot7_Console_Fournisseur",  "provisioning_api.py"),
    "router", "Provisioning /provision/*",
)


# ─── Réconciliation des mesures de réponse ───────────────────────────────────
# Les listes du pare-feu vivent dans la table pf, en mémoire. Un redémarrage de
# l'appliance les vide : une machine mise en quarantaine redeviendrait libre
# sans qu'aucune décision ne l'ait levée, pendant que la console continuerait
# d'afficher « isolée ». Au démarrage, NEXUS repousse donc ce que son audit dit
# être en vigueur.
#
# L'opération ne peut pas empêcher le service de démarrer : un équipement
# éteint produit un écart consigné, pas une exception.
# ─── Ouvrier des dossiers d'enquête ──────────────────────────────────────────
# L'ingestion écrit dans `dossier_sortie` et rend la main : elle ne dépend
# jamais de la disponibilité d'IRIS. Cet ouvrier vide la file en arrière-plan.
#
# Un fil d'exécution plutôt qu'un service séparé : il partage la configuration
# et le cycle de vie du cœur SOC, et il n'y a rien à démarrer en plus le jour de
# la démonstration. Il est « daemon » — l'arrêt du service ne l'attend pas.
@app.on_event("startup")
async def _ouvrier_dossiers():
    if os.getenv("DOSSIERS_ACTIFS", "1").lower() in ("0", "false", "no"):
        print("[run] · ouvrier des dossiers désactivé (DOSSIERS_ACTIFS)")
        return
    try:
        import threading

        import psycopg2
        import psycopg2.extras
        from dossiers import IRIS, boucler
    except ImportError as e:
        print(f"[run] · ouvrier des dossiers non monté — {e}")
        return

    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("[run] · ouvrier des dossiers sans base — DB_DSN absent")
        return

    def fabrique():
        return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    fil = threading.Thread(
        target=boucler,
        args=(fabrique, IRIS()),
        kwargs={"intervalle": int(os.getenv("DOSSIER_CYCLE_S", "20"))},
        name="ouvrier-dossiers", daemon=True)
    fil.start()
    print("[run] ✓ ouvrier des dossiers démarré")


# ─── Veille des escalades ────────────────────────────────────────────────────
# Quand un analyste escalade une alerte dans IRIS, un canal de discussion
# s'ouvre pour la coordination. La veille interroge IRIS à intervalle plutôt
# que d'attendre une notification : IRIS n'expose ses accroches qu'à des
# modules installés dans son conteneur, et faire dépendre l'ouverture d'un
# canal du cadriciel d'un tiers, c'est accepter qu'il cesse un jour sans que
# personne ne s'en aperçoive. Voir discussion/veille.py.
@app.on_event("startup")
async def _veille_escalades():
    if os.getenv("DISCUSSION_ACTIVE", "1").lower() in ("0", "false", "no"):
        print("[run] · veille des escalades désactivée (DISCUSSION_ACTIVE)")
        return
    if not os.getenv("MATTERMOST_TOKEN"):
        print("[run] · veille des escalades en attente — MATTERMOST_TOKEN absent")
        return
    try:
        import threading

        import psycopg2
        import psycopg2.extras
        from discussion import Mattermost, boucler as veiller
        from dossiers import IRIS
    except ImportError as e:
        print(f"[run] · veille des escalades non montée — {e}")
        return

    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("[run] · veille des escalades sans base — DB_DSN absent")
        return

    def fabrique():
        return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    fil = threading.Thread(
        target=veiller,
        args=(fabrique, IRIS(), Mattermost(),
              os.getenv("IRIS_URL", "https://10.50.0.2:4443")),
        name="veille-escalades", daemon=True)
    fil.start()
    print("[run] ✓ veille des escalades démarrée")


@app.on_event("startup")
async def _reconcilier_mesures_au_demarrage():
    module = sys.modules.get("admin_api")
    fonction = getattr(module, "reconcilier_mesures", None) if module else None
    if fonction is None:
        print("[run] · réconciliation ignorée — connecteurs non montés")
        return
    try:
        ecarts = fonction()
    except Exception as e:
        print(f"[run] ✗ réconciliation impossible — {e}")
        return
    if not ecarts:
        print("[run] ✓ réconciliation : aucun écart, les équipements sont à jour")
    else:
        print(f"[run] ⚠ réconciliation : {len(ecarts)} écart(s)")
        for e in ecarts:
            print(f"[run]     {e}")

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

# ─── Redirection racine → connexion ──────────────────────────────────────────
# Outil interne du CENADI : pas de vitrine publique. La racine mène directement
# à la connexion (également start_url de la PWA dans manifest.json).
from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/login.html")

print("[run] NEXUS SOC démarré")
print("[run]   Login    : http://localhost:8000/app/login.html  (PWA start_url)")
print("[run]   Docs     : http://localhost:8000/app/docs.html")
print("[run]   Contact  : http://localhost:8000/app/contact.html")

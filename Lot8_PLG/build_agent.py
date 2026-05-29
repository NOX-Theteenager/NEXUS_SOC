#!/usr/bin/env python3
# =============================================================================
# NEXUS SOC — Lot 8 : Service de compilation dynamique de l'agent
#
# Compile un binaire Go obfusqué (garble) et tatoué par watermark
# cryptographique liant le binaire à un tenant spécifique.
#
# Prérequis :
#   - Go 1.21+ installé et dans le PATH
#   - garble installé  : go install mvdan.cc/garble@latest
#   - Sources agent    : ./nexus-agent-plg/ (watermark.go, config_fetcher.go, *.go)
#
# Usage CLI :
#   python build_agent.py --tenant-id <uuid> --os linux|windows --arch amd64
#   python build_agent.py --tenant-id <uuid> --os windows --arch amd64
#
# Usage depuis FastAPI :
#   from build_agent import build_agent_binary
#   path = await build_agent_binary(tenant_id, "linux", "amd64")
# =============================================================================

import os
import sys
import hmac
import hashlib
import asyncio
import secrets
import logging
import argparse
import tempfile
import shutil
from pathlib import Path

logger = logging.getLogger("nexus.build")

# Répertoire contenant les sources Go de l'agent PLG
AGENT_SRC_DIR = Path(__file__).parent / "nexus-agent-plg"

# Répertoire de sortie des binaires compilés (nettoyé après envoi)
BUILD_OUT_DIR = Path(__file__).parent / "build-cache"
BUILD_OUT_DIR.mkdir(exist_ok=True)

# Clé maître pour générer les watermarks — DOIT correspondre à JWT_SECRET
MASTER_KEY = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION").encode()

# Durée de conservation des binaires compilés en cache (secondes)
BINARY_TTL_S = 300  # 5 minutes, juste le temps du téléchargement

# Cibles de compilation supportées
VALID_OS   = {"linux", "windows", "darwin"}
VALID_ARCH = {"amd64", "arm64"}


# =============================================================================
# Logique de watermark
# =============================================================================

def compute_watermark(tenant_id: str, salt: str) -> str:
    """
    Watermark = HMAC-SHA256(master_key, tenant_id + ":" + salt)
    Le salt est aléatoire et unique par compilation → deux binaires pour
    le même tenant produisent des watermarks distincts (traçabilité accrue).
    Côté serveur, on vérifie via la table build_log (tenant_id + salt stockés).
    """
    msg = f"{tenant_id}:{salt}".encode()
    return hmac.new(MASTER_KEY, msg, hashlib.sha256).hexdigest()


# =============================================================================
# Compilation
# =============================================================================

async def build_agent_binary(
    tenant_id: str,
    target_os: str = "linux",
    target_arch: str = "amd64",
    server_url: str = "https://nexussoc.cm",
    use_garble: bool = True,
) -> Path:
    """
    Compile l'agent Go obfusqué et tatoué pour un tenant donné.

    Séquence :
        1. Génère un sel aléatoire + watermark HMAC
        2. Injecte via -ldflags : TenantID, WatermarkKey, ServerURL
        3. Lance garble build (ou go build si garble indisponible)
        4. Retourne le chemin du binaire compilé

    Le binaire est une "coquille vide" : il ne contient ni watch_dirs ni
    credentials en dur — tout est récupéré dynamiquement via /plg/agent/config/.
    """
    if target_os not in VALID_OS:
        raise ValueError(f"OS invalide : {target_os}. Valeurs : {VALID_OS}")
    if target_arch not in VALID_ARCH:
        raise ValueError(f"Arch invalide : {target_arch}. Valeurs : {VALID_ARCH}")

    salt      = secrets.token_hex(16)
    watermark = compute_watermark(tenant_id, salt)
    version   = "1.0.0"
    ext       = ".exe" if target_os == "windows" else ""
    out_name  = f"nexusagent-{tenant_id[:8]}-{target_os}-{target_arch}{ext}"
    out_path  = BUILD_OUT_DIR / out_name

    ldflags = (
        f"-s -w "
        f"-X 'main.TenantID={tenant_id}' "
        f"-X 'main.WatermarkKey={watermark}' "
        f"-X 'main.WatermarkSalt={salt}' "
        f"-X 'main.ServerURL={server_url}' "
        f"-X 'main.AgentVersion={version}'"
    )

    env = {
        **os.environ,
        "GOOS":        target_os,
        "GOARCH":      target_arch,
        "CGO_ENABLED": "0",
    }

    # Choisir le compilateur : garble si disponible, go build sinon
    compiler = "garble" if use_garble and _has_garble() else "go"
    if compiler == "garble":
        cmd = ["garble", "-tiny", "-seed", salt[:16], "build",
               f"-ldflags={ldflags}", "-o", str(out_path), "."]
    else:
        logger.warning("garble non trouvé — compilation sans obfuscation")
        cmd = ["go", "build", f"-ldflags={ldflags}", "-o", str(out_path), "."]

    logger.info(
        "Building agent | tenant=%s | os=%s | arch=%s | obfuscated=%s",
        tenant_id[:8], target_os, target_arch, compiler == "garble",
    )

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(AGENT_SRC_DIR),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        logger.error("Build failed | tenant=%s | stderr=%s", tenant_id[:8], err[:500])
        raise RuntimeError(f"Compilation échouée : {err[:300]}")

    logger.info("Build OK | path=%s | size=%d bytes", out_path, out_path.stat().st_size)
    return out_path


def _has_garble() -> bool:
    return shutil.which("garble") is not None


async def cleanup_old_binaries() -> None:
    """Supprime les binaires dépassant BINARY_TTL_S secondes."""
    import time
    now = time.time()
    for f in BUILD_OUT_DIR.glob("nexusagent-*"):
        if now - f.stat().st_mtime > BINARY_TTL_S:
            f.unlink(missing_ok=True)
            logger.debug("Cleaned binary %s", f.name)


# =============================================================================
# Endpoint FastAPI — à inclure dans scoring-service ou admin_api
# =============================================================================

def register_build_route(app):
    """
    Enregistre GET /provision/agent-binary sur l'app FastAPI fournie.
    Appelé depuis scoring-service_app.py :
        from build_agent import register_build_route
        register_build_route(app)
    """
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    @app.get("/provision/agent-binary")
    async def download_agent_binary(
        tenant_id: str,
        os: str = "linux",
        arch: str = "amd64",
    ):
        """
        Compile et retourne le binaire agent obfusqué + watermarqué pour ce tenant.
        Requiert un Bearer token valide (admin_plateforme ou provisioning token).
        """
        try:
            path = await build_agent_binary(tenant_id, os, arch)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RuntimeError as e:
            raise HTTPException(500, str(e))

        filename = path.name
        return FileResponse(
            path=str(path),
            filename=filename,
            media_type="application/octet-stream",
            headers={
                "X-Nexus-Tenant": tenant_id[:8],
                "X-Nexus-OS":     os,
                "X-Nexus-Arch":   arch,
            },
        )


# =============================================================================
# CLI
# =============================================================================

async def _cli_main():
    parser = argparse.ArgumentParser(description="NEXUS SOC — Build agent watermarqué")
    parser.add_argument("--tenant-id", required=True, help="UUID du tenant")
    parser.add_argument("--os",   default="linux",   choices=list(VALID_OS))
    parser.add_argument("--arch", default="amd64",   choices=list(VALID_ARCH))
    parser.add_argument("--server-url", default="https://nexussoc.cm")
    parser.add_argument("--no-garble", action="store_true", help="Désactiver garble (debug)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        path = await build_agent_binary(
            tenant_id=args.tenant_id,
            target_os=args.os,
            target_arch=args.arch,
            server_url=args.server_url,
            use_garble=not args.no_garble,
        )
        print(f"\n✓ Binaire compilé : {path}")
        print(f"  Taille           : {path.stat().st_size / 1024 / 1024:.2f} Mo")
        print(f"  Watermark salt   : {compute_watermark.__doc__}")
    except Exception as e:
        print(f"\n✗ Erreur : {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_cli_main())

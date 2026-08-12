#!/usr/bin/env bash
# =============================================================================
# CENADI Scénario 4 : ACTIVITÉ DE FOND — le quotidien d'un serveur administratif
# =============================================================================
# À exécuter SUR une VM surveillée (vm-app-gov, vm-antilope, vm-rssi).
#
#   sudo bash 04-activite-de-fond.sh                 # 60 min, intensité normale
#   sudo bash 04-activite-de-fond.sh --duree 240
#   sudo bash 04-activite-de-fond.sh --install       # service systemd permanent
#   sudo bash 04-activite-de-fond.sh --purge         # retire tout
#
# POURQUOI CE SCRIPT
# ------------------
# Les trois autres scénarios produisent des INCIDENTS. Il manquait le reste :
# le bruit de fond d'une machine qui travaille. Sans lui, les modèles
# n'apprennent le normal que sur une VM au repos, et le tableau de bord d'une
# soutenance montre des lignes plates coupées de pics.
#
# CE QUE CE SCRIPT NE FAIT PAS
# ----------------------------
# Il n'écrit RIEN dans la base et n'envoie aucune télémétrie. Il se contente de
# faire réellement travailler la machine : fichiers écrits, archives compressées,
# requêtes réseau, processus lancés. C'est l'agent qui mesure, comme pour
# n'importe quelle charge réelle. Aucune donnée n'est fabriquée.
#
# Il reste VOLONTAIREMENT sous les seuils de détection : transferts sous 1 Mo,
# aucun compte créé, aucun port C2, aucune lecture de fichier sensible. Si ce
# script déclenchait une alerte, ce serait un faux positif — et c'est justement
# une mesure utile de la qualité du modèle.
# =============================================================================
set -uo pipefail

DUREE_MIN=60
INTENSITE=normale
ACTION=executer
RACINE=/srv/cenadi-dossiers
SERVICE=/etc/systemd/system/nexus-activite-fond.service

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duree)     DUREE_MIN="${2:-60}"; shift 2 ;;
    --intensite) INTENSITE="${2:-normale}"; shift 2 ;;
    --install)   ACTION=install; shift ;;
    --purge)     ACTION=purge;   shift ;;
    -h|--help)   sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; exit 1 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "À exécuter avec sudo." >&2; exit 1; }

case "$INTENSITE" in
  faible)  PAUSE_MAX=90; LOT_MAX=3  ;;
  normale) PAUSE_MAX=35; LOT_MAX=8  ;;
  forte)   PAUSE_MAX=12; LOT_MAX=18 ;;
  *) echo "Intensité : faible | normale | forte" >&2; exit 1 ;;
esac

# ── Purge ───────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "purge" ]]; then
  systemctl disable --now nexus-activite-fond.service 2>/dev/null || true
  rm -f "$SERVICE"; systemctl daemon-reload 2>/dev/null || true
  rm -rf "$RACINE"
  echo "✓ Activité de fond retirée, $RACINE supprimé."
  exit 0
fi

# ── Installation en service ─────────────────────────────────────────────────
if [[ "$ACTION" == "install" ]]; then
  install -m 0755 "$0" /usr/local/bin/nexus-activite-fond.sh
  cat > "$SERVICE" <<EOF
[Unit]
Description=NEXUS SOC — activité de fond réaliste (bruit administratif)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/nexus-activite-fond.sh --duree 1440 --intensite ${INTENSITE}
Restart=always
RestartSec=30
Nice=15
IOSchedulingClass=idle

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now nexus-activite-fond.service
  echo "✓ Service installé et démarré (intensité ${INTENSITE})."
  echo "  Suivi   : journalctl -u nexus-activite-fond -f"
  echo "  Retrait : sudo $0 --purge"
  exit 0
fi

# ── Préparation ─────────────────────────────────────────────────────────────
SERVICES=(finances personnel courrier archives marches)
mkdir -p "$RACINE"
for s in "${SERVICES[@]}"; do mkdir -p "$RACINE/$s"; done

# Cible réseau : l'adresse du SOC telle que l'agent l'a enregistrée à
# l'enrôlement. La passerelle par défaut ne convient pas — dans l'architecture
# segmentée, elle ne mène pas au cœur SOC.
CONF_AGENT="${NEXUS_AGENT_DIR:-/etc/nexus-agent}/agent.json"
if [[ -z "${SOC:-}" && -r "$CONF_AGENT" ]]; then
  SOC=$(python3 - "$CONF_AGENT" <<'PY' 2>/dev/null
import json, sys, urllib.parse
try:
    u = json.load(open(sys.argv[1])).get("soc_url", "")
    print(urllib.parse.urlparse(u).hostname or "")
except Exception:
    print("")
PY
)
fi
SOC=${SOC:-}
[[ -z "$SOC" ]] && echo "⚠ Adresse du SOC inconnue : pas de trafic réseau généré." \
                        "Relancer avec SOC=10.50.0.1 $0 …"

nettoyer() {
  echo
  echo "→ Arrêt : conservation de l'arborescence, purge des fichiers temporaires."
  find "$RACINE" -name '*.tmp' -delete 2>/dev/null || true
  exit 0
}
trap nettoyer INT TERM

FIN=$(( $(date +%s) + DUREE_MIN * 60 ))
echo "Activité de fond — ${DUREE_MIN} min, intensité ${INTENSITE}, cible réseau ${SOC:-aucune}"
echo "Arborescence : $RACINE"
echo

# ── Boucle ──────────────────────────────────────────────────────────────────
# Modulation horaire : l'activité se réduit hors 8h–18h, comme un service
# administratif. Le Modèle 2 utilise cette bande horaire ; une charge plate
# 24h/24 lui apprendrait un normal qui n'existe dans aucune administration.
cycles=0
while [[ $(date +%s) -lt $FIN ]]; do
  heure=$(date +%-H)
  if (( heure >= 8 && heure < 18 )); then facteur=1; else facteur=4; fi

  svc=${SERVICES[$RANDOM % ${#SERVICES[@]}]}
  dossier="$RACINE/$svc"
  lot=$(( RANDOM % LOT_MAX + 1 ))

  # 1. Écriture de documents — activité disque et modification de fichiers
  for ((i = 0; i < lot; i++)); do
    f="$dossier/doc-$(date +%Y%m%d)-$RANDOM.txt"
    {
      echo "Service : $svc"
      echo "Émis le : $(date -Is)"
      echo "Référence : REF-$(date +%Y)-$((RANDOM % 9000 + 1000))"
      head -c $(( RANDOM % 4096 + 512 )) /dev/urandom | base64 | head -40
    } > "$f" 2>/dev/null
  done

  # 2. Consultation — lecture, ce que fait un agent qui travaille
  find "$dossier" -type f -name '*.txt' 2>/dev/null | head -20 | while read -r f; do
    wc -c "$f" > /dev/null 2>&1
  done

  # 3. Archivage périodique — compression, pic CPU bref et légitime
  if (( cycles % 7 == 0 )); then
    tar -czf "$dossier/archive-$(date +%H%M%S).tar.gz.tmp" \
        -C "$dossier" . 2>/dev/null || true
  fi

  # 4. Rotation — une machine réelle ne grossit pas indéfiniment
  nb=$(find "$dossier" -type f | wc -l)
  if (( nb > 400 )); then
    find "$dossier" -type f -printf '%T@ %p\n' 2>/dev/null \
      | sort -n | head -150 | cut -d' ' -f2- | xargs -r rm -f
  fi

  # 5. Trafic réseau — sous le seuil d'export (1 Mo), donc jamais signalé
  if [[ -n "${SOC:-}" ]]; then
    for ((i = 0; i < 3; i++)); do
      python3 - "$SOC" <<'PY' 2>/dev/null || true
import socket, sys
try:
    s = socket.create_connection((sys.argv[1], 8000), timeout=3)
    s.sendall(b"GET /health HTTP/1.1\r\nHost: nexus\r\nConnection: close\r\n\r\n")
    s.recv(4096); s.close()
except Exception:
    pass
PY
    done
  fi

  cycles=$((cycles + 1))
  if (( cycles % 10 == 0 )); then
    echo "  $(date +%H:%M:%S) — $cycles cycles, $(find "$RACINE" -type f | wc -l) fichiers"
  fi

  sleep $(( (RANDOM % PAUSE_MAX + 5) * facteur ))
done

nettoyer

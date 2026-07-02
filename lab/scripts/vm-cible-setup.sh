#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Setup de vm-cible (10.42.0.20)
# =============================================================================
# Ubuntu 22.04 Server jouant le rôle d'un poste comptable simulé (MINFI).
#
# Cette VM :
#   • Émet de la télémétrie normale (bruit de fond réaliste)
#   • Peut être scriptée pour émettre des patterns anormaux (fraude UEBA)
#   • Peut être "infectée" par le scénario ransomware
#   • A un utilisateur "compta_agent" qui simule un employé
#
# Prérequis :
#   • ip a → 10.42.0.20/24
#   • vm-soc DOIT être installée et accessible sur 10.42.0.10:8000
# =============================================================================
set -euo pipefail

TENANT_MINFI="MINFI"
AGENT_HOSTNAME="POSTE-COMPTA-01"
SOC_HOST="10.42.0.10"      # vm-soc
SOC_URL="http://${SOC_HOST}:8000"    # ingest direct sans TLS (LAN interne)

# ── 0. Vérifier connectivité vm-soc ─────────────────────────────────────────
echo "═══ 0/5 Vérification vm-soc ═══"
if ! curl -s "${SOC_URL}/health" | grep -q '"status":"ok"'; then
    echo "✗ vm-soc (${SOC_URL}) injoignable ou pas prête."
    echo "  Faire d'abord tourner scripts/vm-soc-setup.sh sur vm-soc."
    exit 1
fi
echo "✓ vm-soc accessible."

# ── 1. Paquets système ──────────────────────────────────────────────────────
echo "═══ 1/5 Paquets système ═══"
sudo apt-get update
sudo apt-get install -y \
    curl jq \
    python3 python3-pip python3-venv \
    net-tools htop \
    openssl coreutils    # openssl pour la simu chiffrement

# ── 2. Compte 'compta_agent' avec profil réaliste ───────────────────────────
echo "═══ 2/5 Utilisateur compta_agent ═══"
if ! id compta_agent >/dev/null 2>&1; then
    sudo useradd -m -s /bin/bash compta_agent
    echo "compta_agent:compta" | sudo chpasswd
fi
# Créer des dossiers de travail simulés
sudo -u compta_agent bash <<'BASH'
mkdir -p ~/Documents/Rapports ~/Documents/Mandats ~/Documents/Budgets
for i in {1..20}; do
    echo "Rapport financier ${i} - MINFI - $(date -I)" > ~/Documents/Rapports/rapport_$i.txt
    echo "Mandat de paiement N°$i - Bénéficiaire: Fournisseur_$i - Montant: $((RANDOM % 500000)) FCFA" > ~/Documents/Mandats/mandat_$i.txt
    echo "Budget exercice 2026 - Section $i - Allocation: $((RANDOM % 10000000)) FCFA" > ~/Documents/Budgets/budget_$i.txt
done
BASH
echo "✓ 60 fichiers créés dans ~compta_agent/Documents (cible du ransomware)"

# ── 3. Enregistrer un agent NEXUS auprès du SOC ─────────────────────────────
echo "═══ 3/5 Enregistrement agent NEXUS ═══"
# Récupérer un JWT admin (compte de démo, mdp 'admin')
ACCESS_TOKEN=$(curl -s -X POST "${SOC_URL}/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | jq -r '.access_token // empty')

if [[ -z "$ACCESS_TOKEN" ]]; then
    echo "✗ Login admin échoué. Vérifier que le seed demo a été appliqué sur vm-soc."
    exit 1
fi

# Créer un token de provisioning pour le tenant MINFI
PROV=$(curl -s -X POST "${SOC_URL}/provision/token" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_name\":\"${TENANT_MINFI}\",\"hostname\":\"${AGENT_HOSTNAME}\"}")

BEARER=$(echo "$PROV" | jq -r '.bearer // .token // empty')
AGENT_ID=$(echo "$PROV" | jq -r '.agent_id // empty')

if [[ -z "$BEARER" ]]; then
    echo "✗ Provisioning refusé. Réponse : $PROV"
    exit 1
fi
echo "✓ Agent enregistré : id=${AGENT_ID}"

# Sauvegarder le token pour les scénarios
sudo mkdir -p /etc/nexus-agent
echo "$BEARER" | sudo tee /etc/nexus-agent/bearer >/dev/null
echo "$AGENT_ID" | sudo tee /etc/nexus-agent/agent_id >/dev/null
sudo chmod 600 /etc/nexus-agent/*
echo "SOC_URL=${SOC_URL}"       | sudo tee /etc/nexus-agent/env  >/dev/null
echo "AGENT_HOSTNAME=${AGENT_HOSTNAME}" | sudo tee -a /etc/nexus-agent/env >/dev/null

# ── 4. Client d'ingestion en Python (simplifié pour le lab) ─────────────────
echo "═══ 4/5 Client d'ingestion ═══"
sudo tee /usr/local/bin/nexus-emit >/dev/null <<'PYEOF'
#!/usr/bin/env python3
"""Émet un événement de télémétrie vers le SOC (JSON POST)."""
import json, sys, urllib.request, urllib.error, os

with open("/etc/nexus-agent/bearer") as f: BEARER = f.read().strip()
with open("/etc/nexus-agent/env") as f:
    env = dict(l.strip().split("=", 1) for l in f if "=" in l)

payload = json.loads(sys.stdin.read())
payload.setdefault("hostname", env.get("AGENT_HOSTNAME", "unknown"))

req = urllib.request.Request(
    f"{env['SOC_URL']}/ingest",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {BEARER}"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
    sys.exit(1)
PYEOF
sudo chmod +x /usr/local/bin/nexus-emit

# ── 5. Générateur de bruit de fond (activité "normale") ─────────────────────
echo "═══ 5/5 Bruit de fond ═══"
sudo tee /usr/local/bin/nexus-normal-noise >/dev/null <<'BASH'
#!/usr/bin/env bash
# Émet une télémétrie "normale" toutes les 30 secondes.
# Représente l'activité d'un agent comptable régulier.
while true; do
    HOUR=$(date +%H)
    # Amplitude adaptée aux horaires de bureau (8h-17h)
    if (( HOUR >= 8 && HOUR <= 17 )); then
        AMPLITUDE=1.0
    else
        AMPLITUDE=0.1
    fi

    cat <<JSON | nexus-emit
{
  "type": "user_activity",
  "user": "compta_agent",
  "action": "file_read",
  "count": $(awk -v a=$AMPLITUDE 'BEGIN{srand(); print int(3+rand()*10*a)}'),
  "size_bytes": $(awk -v a=$AMPLITUDE 'BEGIN{srand(); print int(1024+rand()*50000*a)}'),
  "ts": "$(date --iso-8601=seconds)"
}
JSON
    sleep 30
done
BASH
sudo chmod +x /usr/local/bin/nexus-normal-noise

# Service systemd pour le bruit de fond (activable pendant la démo)
sudo tee /etc/systemd/system/nexus-normal-noise.service >/dev/null <<UNIT
[Unit]
Description=NEXUS SOC LAB - Bruit de fond activité normale
After=network-online.target

[Service]
ExecStart=/usr/local/bin/nexus-normal-noise
Restart=on-failure
User=nobody

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
# Ne PAS démarrer maintenant — activé au moment de la démo pour ne pas polluer
# les timestamps.

# ── Résumé ──────────────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Setup vm-cible terminé"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Utilisateur cible  : compta_agent (mdp: compta)"
echo "  Fichiers à cibler  : ~compta_agent/Documents/{Rapports,Mandats,Budgets}"
echo "  Agent NEXUS ID     : $(cat /etc/nexus-agent/agent_id)"
echo "  Bearer token       : /etc/nexus-agent/bearer (root only)"
echo
echo "  Commandes de test :"
echo "    echo '{\"type\":\"test\",\"level\":\"info\"}' | nexus-emit"
echo
echo "  Scénarios à jouer depuis cette VM :"
echo "    sudo scenarios/02-fraude-ueba.sh"
echo "    sudo scenarios/03-ransomware-soar.sh"
echo
echo "  Activer le bruit de fond (avant la démo) :"
echo "    sudo systemctl start nexus-normal-noise"
echo "════════════════════════════════════════════════════════════════════"

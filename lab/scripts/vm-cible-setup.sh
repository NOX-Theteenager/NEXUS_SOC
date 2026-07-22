#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Setup de vm-cible (10.42.10.20)
# =============================================================================
# Ubuntu 22.04 Server jouant le rôle d'un poste comptable Afriland (VLAN 10).
#
# Cette VM :
#   • Émet de la télémétrie normale (bruit de fond réaliste)
#   • Peut être scriptée pour émettre des patterns anormaux (fraude UEBA)
#   • Peut être "infectée" par le scénario ransomware
#   • A un utilisateur "compta_agent" qui simule un employé
#
# Prérequis :
#   • ip a → 10.42.10.20/24
#   • le HÔTE SOC DOIT être accessible sur 10.42.0.1:8000 (via routeur MikroTik)
# =============================================================================
set -euo pipefail

# Tenant Afriland : client de test principal (VLAN 10 dans le lab)
TENANT_AFRILAND="Afriland First Bank Microfinance"
AGENT_HOSTNAME="POSTE-COMPTA-01"           # doit matcher le seed_demo
SOC_HOST="10.42.0.1"                        # HÔTE (route MikroTik VLAN 10 → mgmt)
SOC_URL="http://${SOC_HOST}:8000"           # ingest direct sans TLS (LAN interne)

# ── 0. Vérifier connectivité HÔTE SOC ───────────────────────────────────────
echo "═══ 0/5 Vérification HÔTE SOC ═══"
if ! curl -s "${SOC_URL}/health" | grep -q '"status":"ok"'; then
    echo "✗ HÔTE SOC (${SOC_URL}) injoignable ou pas prêt."
    echo "  Vérifier : (1) host-configure.sh a bien tourné sur le hôte,"
    echo "             (2) le routeur MikroTik route VLAN 10 → mgmt (10.42.0.1)."
    exit 1
fi
echo "✓ HÔTE SOC accessible."

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
    echo "Rapport financier ${i} - Afriland First Bank - $(date -I)" > ~/Documents/Rapports/rapport_$i.txt
    echo "Mandat de paiement N°$i - Bénéficiaire: Fournisseur_$i - Montant: $((RANDOM % 500000)) FCFA" > ~/Documents/Mandats/mandat_$i.txt
    echo "Budget exercice 2026 - Section $i - Allocation: $((RANDOM % 10000000)) FCFA" > ~/Documents/Budgets/budget_$i.txt
done
BASH
echo "✓ 60 fichiers créés dans ~compta_agent/Documents (cible du ransomware)"

# ── 3. Enregistrer un agent NEXUS auprès du SOC ─────────────────────────────
echo "═══ 3/5 Enregistrement agent NEXUS ═══"
# Récupérer un JWT admin (compte de démo, mdp 'admin')
ACCESS_TOKEN=$(curl -s -X POST "${SOC_URL}/auth/token" \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | jq -r '.access_token // empty')

if [[ -z "$ACCESS_TOKEN" ]]; then
    echo "✗ Login admin échoué. Vérifier que le seed demo a été appliqué sur le HÔTE SOC."
    exit 1
fi

# Résoudre le tenant_id (UUID) depuis le nom via /admin/tenants
TENANT_ID=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" "${SOC_URL}/admin/tenants" \
    | jq -r --arg n "$TENANT_AFRILAND" '.[] | select(.nom==$n) | .id' | head -1)

if [[ -z "$TENANT_ID" ]]; then
    echo "✗ Tenant « ${TENANT_AFRILAND} » introuvable. Le seed a-t-il été appliqué ?"
    exit 1
fi
echo "  tenant_id = ${TENANT_ID}"

# Créer un token de provisioning (l'API attend tenant_id, pas tenant_name).
# one_time=false → token réutilisable pour la télémétrie continue du lab.
PROV=$(curl -s -X POST "${SOC_URL}/provision/token" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"${TENANT_ID}\",\"hostname\":\"${AGENT_HOSTNAME}\",\"os\":\"linux\",\"one_time\":false}")

BEARER=$(echo "$PROV" | jq -r '.bearer_token // empty')
AGENT_ID=$(echo "$PROV" | jq -r '.agent_id // empty')
HMAC_KEY=$(echo "$PROV" | jq -r '.hmac_key // empty')

if [[ -z "$BEARER" ]]; then
    echo "✗ Provisioning refusé. Réponse : $PROV"
    exit 1
fi
echo "✓ Agent enregistré : id=${AGENT_ID}"

# Sauvegarder les identifiants pour les scénarios (bearer + hmac + ids)
sudo mkdir -p /etc/nexus-agent
echo "$BEARER"   | sudo tee /etc/nexus-agent/bearer   >/dev/null
echo "$HMAC_KEY" | sudo tee /etc/nexus-agent/hmac_key >/dev/null
echo "$AGENT_ID" | sudo tee /etc/nexus-agent/agent_id >/dev/null
sudo chmod 600 /etc/nexus-agent/*
sudo tee /etc/nexus-agent/env >/dev/null <<EOF
SOC_URL=${SOC_URL}
AGENT_HOSTNAME=${AGENT_HOSTNAME}
AGENT_ID=${AGENT_ID}
TENANT_ID=${TENANT_ID}
EOF

# ── 4. Client d'ingestion en Python (format /ingest + signature HMAC) ───────
echo "═══ 4/5 Client d'ingestion ═══"
sudo tee /usr/local/bin/nexus-emit >/dev/null <<'PYEOF'
#!/usr/bin/env python3
"""Émet un événement de télémétrie vers le SOC.

Contrat /ingest :
  - Body  : {"agent_id", "tenant_id", "events":[<event>]}
  - Header: Authorization: Bearer nexus_...  +  X-Signature: HMAC-SHA256(hmac_key, body)
"""
import json, sys, os, hmac, hashlib, urllib.request, urllib.error

with open("/etc/nexus-agent/bearer") as f:   BEARER = f.read().strip()
with open("/etc/nexus-agent/hmac_key") as f: HMAC_KEY = f.read().strip()
with open("/etc/nexus-agent/env") as f:
    env = dict(l.strip().split("=", 1) for l in f if "=" in l and not l.startswith("#"))

event = json.loads(sys.stdin.read())
event.setdefault("hostname", env.get("AGENT_HOSTNAME", "unknown"))

batch = {
    "agent_id":  env.get("AGENT_ID", ""),
    "tenant_id": env.get("TENANT_ID", ""),
    "events":    [event],
}
body = json.dumps(batch).encode()
sig  = hmac.new(HMAC_KEY.encode(), body, hashlib.sha256).hexdigest()

req = urllib.request.Request(
    f"{env['SOC_URL']}/ingest",
    data=body,
    headers={
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {BEARER}",
        "X-Signature":   sig,
    },
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

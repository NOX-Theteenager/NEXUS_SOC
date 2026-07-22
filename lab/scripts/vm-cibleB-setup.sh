#!/usr/bin/env sh
# =============================================================================
# NEXUS SOC LAB — Setup de vm-cibleB (10.42.20.20)
# =============================================================================
# Alpine Linux 3.19 (léger : 2 Go RAM, 8 Go disque, ~50 Mo ISO).
#
# Rôle : représenter le client UBA (VLAN 20). Cette VM n'est PAS utilisée
# pour les tests de fraude/ransomware — elle sert exclusivement à :
#
#   1) Rendre l'isolation cross-tenant TANGIBLE (bloc physique visible
#      dans virt-manager + trafic ARP différent dans tcpdump).
#   2) Émettre un peu de télémétrie normale UBA pour que le tenant UBA
#      apparaisse comme "vivant" dans la console admin.
#   3) Servir de cible aux tests d'échec de scan depuis vm-kali.
#
# NB : script en /bin/sh (Alpine n'a pas bash par défaut).
# =============================================================================

TENANT_UBA="UBA Cameroun Microfinance"    # doit matcher le nom exact du seed_demo
AGENT_HOSTNAME="SRV-CORE-01"     # correspond au seed_demo (SRV-CORE-01 tenant UBA)
SOC_HOST="10.42.0.1"             # HÔTE via gateway libvirt (route MikroTik vers mgmt)
SOC_URL="http://${SOC_HOST}:8000"

# ── 0. Vérifier connectivité SOC ────────────────────────────────────────────
echo "═══ 0/4 Connectivité SOC ═══"
if ! wget -qO- --timeout=5 "${SOC_URL}/health" | grep -q '"status":"ok"'; then
    echo "✗ SOC ${SOC_URL} injoignable."
    echo "  Vérifier que le routeur MikroTik (VLAN 20 → mgmt) a bien"
    echo "  autorisé le trafic vers 10.42.0.1."
    exit 1
fi
echo "✓ SOC accessible"

# ── 1. Paquets Alpine ───────────────────────────────────────────────────────
echo "═══ 1/4 Paquets Alpine ═══"
apk add --no-cache curl jq openssl coreutils

# ── 2. Enregistrer l'agent NEXUS pour le tenant UBA ─────────────────────────
echo "═══ 2/4 Enregistrement agent NEXUS (tenant UBA) ═══"
ACCESS_TOKEN=$(curl -s -X POST "${SOC_URL}/auth/token" \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | jq -r '.access_token // empty')

if [ -z "$ACCESS_TOKEN" ]; then
    echo "✗ Login admin échoué"
    exit 1
fi

# Résoudre le tenant_id (UUID) depuis le nom via /admin/tenants
TENANT_ID=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" "${SOC_URL}/admin/tenants" \
    | jq -r --arg n "$TENANT_UBA" '.[] | select(.nom==$n) | .id' | head -1)

if [ -z "$TENANT_ID" ]; then
    echo "✗ Tenant « ${TENANT_UBA} » introuvable. Seed appliqué ?"
    exit 1
fi

# L'API attend tenant_id (UUID), pas tenant_name ; la réponse contient bearer_token
PROV=$(curl -s -X POST "${SOC_URL}/provision/token" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"${TENANT_ID}\",\"hostname\":\"${AGENT_HOSTNAME}\",\"os\":\"linux\",\"one_time\":false}")

BEARER=$(echo "$PROV" | jq -r '.bearer_token // empty')
AGENT_ID=$(echo "$PROV" | jq -r '.agent_id // empty')
HMAC_KEY=$(echo "$PROV" | jq -r '.hmac_key // empty')

if [ -z "$BEARER" ]; then
    echo "✗ Provisioning refusé : $PROV"
    exit 1
fi

mkdir -p /etc/nexus-agent
echo "$BEARER"   > /etc/nexus-agent/bearer
echo "$HMAC_KEY" > /etc/nexus-agent/hmac_key
echo "$AGENT_ID" > /etc/nexus-agent/agent_id
chmod 600 /etc/nexus-agent/*
cat > /etc/nexus-agent/env <<EOF
SOC_URL=${SOC_URL}
AGENT_HOSTNAME=${AGENT_HOSTNAME}
AGENT_ID=${AGENT_ID}
TENANT_ID=${TENANT_ID}
EOF

echo "✓ Agent enregistré : id=${AGENT_ID}"

# ── 3. Client d'ingestion (format /ingest + signature HMAC) ─────────────────
echo "═══ 3/4 Client d'ingestion ═══"
cat > /usr/local/bin/nexus-emit <<'SH'
#!/bin/sh
# Émet un événement vers le SOC au format /ingest attendu :
#   Body   : {"agent_id","tenant_id","events":[<event>]}
#   Header : Authorization: Bearer + X-Signature: HMAC-SHA256(hmac_key, body)
. /etc/nexus-agent/env
BEARER=$(cat /etc/nexus-agent/bearer)
HMAC_KEY=$(cat /etc/nexus-agent/hmac_key)
EVENT=$(cat)   # event JSON depuis stdin
BODY="{\"agent_id\":\"${AGENT_ID}\",\"tenant_id\":\"${TENANT_ID}\",\"events\":[${EVENT}]}"
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$HMAC_KEY" | awk '{print $NF}')
curl -s -X POST "${SOC_URL}/ingest" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER" \
    -H "X-Signature: $SIG" \
    -d "$BODY"
SH
chmod +x /usr/local/bin/nexus-emit

# ── 4. Bruit de fond UBA (activité minimale, pas de patterns anormaux) ──────
echo "═══ 4/4 Service bruit de fond ═══"
cat > /etc/init.d/nexus-uba-noise <<'INIT'
#!/sbin/openrc-run
description="NEXUS SOC LAB - Bruit de fond UBA (télémétrie normale)"
command="/usr/local/bin/nexus-uba-noise"
command_background=true
pidfile="/run/nexus-uba-noise.pid"
INIT

cat > /usr/local/bin/nexus-uba-noise <<'BASH'
#!/bin/sh
# Émet 1 événement toutes les 60 s pour que UBA "vive" dans la console SOC.
# Ne génère JAMAIS de pattern anormal — c'est un tenant sain, contrepoint
# au tenant Afriland qui subit les attaques.
while true; do
    HOUR=$(date +%H)
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -le 17 ]; then
        AMPL=5
    else
        AMPL=1
    fi
    cat <<EOF | nexus-emit >/dev/null 2>&1
{
  "type": "user_activity",
  "user": "guichetier_uba",
  "action": "consultation_compte",
  "count": ${AMPL},
  "size_bytes": $((AMPL * 1024)),
  "ts": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    sleep 60
done
BASH
chmod +x /etc/init.d/nexus-uba-noise /usr/local/bin/nexus-uba-noise

# Ne pas démarrer au boot par défaut — activé pendant la démo pour ne pas
# saturer la DB de bruit inutile.
# Pour démarrer : rc-service nexus-uba-noise start

echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Setup vm-cibleB (UBA) terminé"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Tenant représenté : UBA Cameroun Microfinance"
echo "  Hostname NEXUS   : ${AGENT_HOSTNAME}"
echo "  Agent NEXUS ID   : $(cat /etc/nexus-agent/agent_id)"
echo
echo "  Rôle démo :"
echo "    • Preuve d'isolation VLAN — vm-kali essaie nmap → échoue"
echo "    • Preuve d'isolation RLS — dsi@uba.cm ne voit pas les alertes Afriland"
echo "    • Bruit de fond léger si activé (rc-service nexus-uba-noise start)"
echo
echo "  Compte DSI UBA : dsi@uba.cm / admin"
echo "════════════════════════════════════════════════════════════════════"

#!/usr/bin/env bash
# =============================================================================
# CENADI : setup vm-app-gov (10.50.20.20) — serveur applicatif gouvernemental
# =============================================================================
# Installe l'agent NEXUS (télémétrie signée HMAC) pour la zone applicative.
# Réutilise le contrat /ingest correct : tenant_id + bearer_token + X-Signature.
# =============================================================================
set -euo pipefail
SOC=10.50.0.1
SOC_URL="http://${SOC}:8000"
AGENT_HOSTNAME="SRV-APP-GOV-01"
# En souverain mono-tenant CENADI, on rattache à un tenant "CENADI".
TENANT_NAME="CENADI"

echo "═══ 0/4 Connectivité SOC ═══"
curl -s "${SOC_URL}/health" | grep -q '"status":"ok"' || { echo "✗ SOC injoignable ($SOC_URL)"; exit 1; }
echo "✓ SOC souverain accessible"

echo "═══ 1/4 Paquets ═══"
sudo apt-get update -qq && sudo apt-get install -y -qq curl jq python3 openssl coreutils

echo "═══ 2/4 Provisioning agent ═══"
AT=$(curl -s -X POST "${SOC_URL}/auth/token" -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | jq -r '.access_token // empty')
[[ -z "$AT" ]] && { echo "✗ Login admin échoué"; exit 1; }

# tenant_id : crée le tenant CENADI s'il n'existe pas, sinon le résout
TID=$(curl -s -H "Authorization: Bearer $AT" "${SOC_URL}/admin/tenants" \
    | jq -r --arg n "$TENANT_NAME" '.[] | select(.nom==$n) | .id' | head -1)
if [[ -z "$TID" ]]; then
    TID=$(curl -s -X POST "${SOC_URL}/admin/tenants" -H "Authorization: Bearer $AT" \
        -H "Content-Type: application/json" \
        -d '{"nom":"CENADI","type":"administration","offre":"contrat_public"}' | jq -r '.id')
    echo "  tenant CENADI créé : $TID"
fi

PROV=$(curl -s -X POST "${SOC_URL}/provision/token" -H "Authorization: Bearer $AT" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"$TID\",\"hostname\":\"$AGENT_HOSTNAME\",\"os\":\"linux\",\"one_time\":false}")
BEARER=$(echo "$PROV" | jq -r '.bearer_token // empty')
AID=$(echo "$PROV" | jq -r '.agent_id // empty')
HMAC=$(echo "$PROV" | jq -r '.hmac_key // empty')
[[ -z "$BEARER" ]] && { echo "✗ Provisioning refusé : $PROV"; exit 1; }
echo "✓ Agent enregistré : $AID"

sudo mkdir -p /etc/nexus-agent
echo "$BEARER" | sudo tee /etc/nexus-agent/bearer   >/dev/null
echo "$HMAC"   | sudo tee /etc/nexus-agent/hmac_key >/dev/null
sudo chmod 600 /etc/nexus-agent/*
sudo tee /etc/nexus-agent/env >/dev/null <<EOF
SOC_URL=${SOC_URL}
AGENT_HOSTNAME=${AGENT_HOSTNAME}
AGENT_ID=${AID}
TENANT_ID=${TID}
EOF

echo "═══ 3/4 Client d'ingestion (format /ingest + HMAC) ═══"
sudo tee /usr/local/bin/nexus-emit >/dev/null <<'PYEOF'
#!/usr/bin/env python3
import json, sys, os, hmac, hashlib, urllib.request, urllib.error
with open("/etc/nexus-agent/bearer") as f:   BEARER = f.read().strip()
with open("/etc/nexus-agent/hmac_key") as f: HMAC_KEY = f.read().strip()
with open("/etc/nexus-agent/env") as f:
    env = dict(l.strip().split("=",1) for l in f if "=" in l and not l.startswith("#"))
event = json.loads(sys.stdin.read()); event.setdefault("hostname", env.get("AGENT_HOSTNAME","?"))
batch = {"agent_id": env.get("AGENT_ID",""), "tenant_id": env.get("TENANT_ID",""), "events":[event]}
body = json.dumps(batch).encode()
sig = hmac.new(HMAC_KEY.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(f"{env['SOC_URL']}/ingest", data=body, method="POST",
    headers={"Content-Type":"application/json","Authorization":f"Bearer {BEARER}","X-Signature":sig})
try:
    with urllib.request.urlopen(req, timeout=5) as r: print(r.read().decode())
except urllib.error.HTTPError as e: print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr); sys.exit(1)
PYEOF
sudo chmod +x /usr/local/bin/nexus-emit

echo "═══ 4/4 Test ═══"
echo '{"type":"test","level":"info"}' | nexus-emit && echo "✓ Télémétrie OK" || echo "⚠ échec ingest"

echo
echo "✓ Setup vm-app-gov terminé (tenant CENADI, hostname $AGENT_HOSTNAME)"
echo "  Scénario : sudo scenarios/03-exfiltration-solde.sh"

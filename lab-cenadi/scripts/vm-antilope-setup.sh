#!/usr/bin/env bash
# =============================================================================
# CENADI : setup vm-antilope (10.50.30.30) — ZONE SENSIBLE AIR-GAP
# =============================================================================
# Simule le serveur ANTILOPE/SIGIPES (solde de l'État). En air-gap : il ne
# peut QU'émettre sa télémétrie vers le SOC. Ce script est identique à
# vm-app-gov mais avec le hostname ANTILOPE et un rappel sur l'air-gap.
#
# PRÉREQUIS : l'ACL MikroTik doit autoriser 10.50.30.0/24 → 10.50.0.1 (SOC)
# et DROP tout le reste (voir SECURISATION.md couche 2).
# =============================================================================
set -euo pipefail
SOC=10.50.0.1
SOC_URL="http://${SOC}:8000"
AGENT_HOSTNAME="SRV-ANTILOPE-01"
TENANT_NAME="CENADI"

echo "═══ 0/4 Connectivité SOC (seul flux autorisé en air-gap) ═══"
if ! curl -s --max-time 3 "${SOC_URL}/health" | grep -q '"status":"ok"'; then
    echo "✗ SOC injoignable. En air-gap, SEUL 10.50.0.1 doit être joignable."
    echo "  Vérifier l'ACL MikroTik : zone 30 → SOC autorisé, reste DROP."
    exit 1
fi
echo "✓ SOC accessible (flux télémétrie unidirectionnel)"

# Confirmer l'air-gap : Internet et zones latérales DOIVENT échouer
echo "  Contrôle air-gap :"
ping -c1 -W2 8.8.8.8 >/dev/null 2>&1 && echo "    ⚠ Internet joignable — AIR-GAP ROMPU" || echo "    ✓ Internet injoignable"
ping -c1 -W2 10.50.20.20 >/dev/null 2>&1 && echo "    ⚠ zone app joignable — cloisonnement rompu" || echo "    ✓ zones latérales injoignables"

echo "═══ 1/4 Paquets ═══"
sudo apt-get update -qq && sudo apt-get install -y -qq curl jq python3 openssl

echo "═══ 2/4 Provisioning ═══"
AT=$(curl -s -X POST "${SOC_URL}/auth/token" -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | jq -r '.access_token // empty')
TID=$(curl -s -H "Authorization: Bearer $AT" "${SOC_URL}/admin/tenants" \
    | jq -r --arg n "$TENANT_NAME" '.[] | select(.nom==$n) | .id' | head -1)
[[ -z "$TID" ]] && TID=$(curl -s -X POST "${SOC_URL}/admin/tenants" -H "Authorization: Bearer $AT" \
    -H "Content-Type: application/json" -d '{"nom":"CENADI","type":"administration","offre":"contrat_public"}' | jq -r '.id')
PROV=$(curl -s -X POST "${SOC_URL}/provision/token" -H "Authorization: Bearer $AT" \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"$TID\",\"hostname\":\"$AGENT_HOSTNAME\",\"os\":\"linux\",\"one_time\":false}")
BEARER=$(echo "$PROV" | jq -r '.bearer_token // empty'); AID=$(echo "$PROV" | jq -r '.agent_id // empty'); HMAC=$(echo "$PROV" | jq -r '.hmac_key // empty')
[[ -z "$BEARER" ]] && { echo "✗ Provisioning refusé : $PROV"; exit 1; }
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
echo "✓ Agent ANTILOPE enregistré : $AID"

echo "═══ 3/4 Client d'ingestion ═══"
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

echo "═══ 4/4 Test télémétrie ═══"
echo '{"type":"test","zone":"sensible","level":"info"}' | nexus-emit && echo "✓ OK" || echo "⚠ échec"
echo
echo "✓ Setup vm-antilope terminé (ZONE SENSIBLE AIR-GAP)"
echo "  Scénario : sudo scenarios/02-airgap-zone-sensible.sh"

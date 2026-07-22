#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Setup de vm-kali (10.42.30.30)
# =============================================================================
# Kali Linux joue le rôle d'attaquant externe pour le scénario ransomware.
# Rôle : simuler un serveur C2 (Command & Control) qui reçoit les callbacks du
# ransomware installé sur vm-cible.
# =============================================================================
set -euo pipefail

echo "═══ Installation outils ═══"
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip \
    netcat-openbsd tcpdump nmap \
    curl jq

# ── Serveur C2 factice (écoute les callbacks du ransomware simulé) ──────────
sudo mkdir -p /opt/c2-server
sudo tee /opt/c2-server/c2_listener.py >/dev/null <<'PY'
#!/usr/bin/env python3
"""
Serveur C2 factice — écoute les callbacks HTTP du ransomware simulé.
Chaque requête POST est loggée. Ne fait RIEN d'autre.
Objectif : générer du trafic sortant depuis vm-cible vers 10.42.30.30
que le SIEM NEXUS peut détecter comme "communication vers IP non listée".
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
import json, sys

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # on gère nous-mêmes le log

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode(errors="ignore")
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body[:200]}
        stamp = datetime.now().isoformat(timespec="seconds")
        print(f"[{stamp}] {self.client_address[0]} → {self.path} → {data}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"cmd":"continue"}')

    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b'OK')

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8443
    print(f"C2 listener écoute sur 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
PY
sudo chmod +x /opt/c2-server/c2_listener.py

sudo tee /etc/systemd/system/c2-listener.service >/dev/null <<UNIT
[Unit]
Description=C2 Listener (démo NEXUS SOC — n'est PAS un vrai C2)
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/c2-server/c2_listener.py 8443
Restart=on-failure
User=nobody

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable c2-listener
# Ne pas démarrer maintenant — sera activé au moment du scénario ransomware.

echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Setup vm-kali terminé"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  IP attaquante : 10.42.30.30"
echo "  Port C2       : 8443"
echo
echo "  Démarrer le C2 au moment de la démo ransomware :"
echo "    sudo systemctl start c2-listener"
echo "    journalctl -u c2-listener -f    # observer les callbacks reçus"
echo "════════════════════════════════════════════════════════════════════"

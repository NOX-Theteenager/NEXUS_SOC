"""Déploiement du collecteur via l'agent invité QEMU.

    python3 deployer-via-qga.py <domaine-libvirt> [chemin/nexus_collector.py]

Aucun identifiant SSH n'est requis : le canal virtio-serial passe par
l'hyperviseur. Le fichier est transféré par morceaux, son empreinte SHA-256 est
vérifiée SUR LA VM avant installation — un transfert tronqué ne doit pas
remplacer un collecteur qui fonctionne.

Prérequis sur la VM : paquet qemu-guest-agent installé et démarré. Le canal
virtio-serial doit exister côté hyperviseur (il est présent sur les quatre VM
du lab).
"""
import base64, json, subprocess, sys, time

VM  = sys.argv[1]
SRC = sys.argv[2] if len(sys.argv) > 2 else "Lot1_Agent_Go/nexus_collector.py"

def qga(payload):
    r = subprocess.run(["virsh", "-c", "qemu:///system", "qemu-agent-command", VM,
                        json.dumps(payload)], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)["return"]

def executer(cmd, args):
    pid = qga({"execute": "guest-exec",
               "arguments": {"path": cmd, "arg": args, "capture-output": True}})["pid"]
    for _ in range(60):
        st = qga({"execute": "guest-exec-status", "arguments": {"pid": pid}})
        if st.get("exited"):
            dec = lambda k: base64.b64decode(st[k]).decode(errors="replace") if st.get(k) else ""
            return st.get("exitcode", -1), dec("out-data"), dec("err-data")
        time.sleep(0.5)
    raise RuntimeError("délai dépassé")

# 1. Écriture du fichier dans /tmp par morceaux
donnees = open(SRC, "rb").read()
h = qga({"execute": "guest-file-open",
         "arguments": {"path": "/tmp/nexus_collector.py", "mode": "wb"}})
for i in range(0, len(donnees), 48000):
    qga({"execute": "guest-file-write",
         "arguments": {"handle": h,
                       "buf-b64": base64.b64encode(donnees[i:i+48000]).decode()}})
qga({"execute": "guest-file-close", "arguments": {"handle": h}})
print(f"  fichier transféré : {len(donnees)} octets")

# 2. Contrôle d'intégrité AVANT toute installation
import hashlib
attendu = hashlib.sha256(donnees).hexdigest()
code, out, err = executer("/usr/bin/sha256sum", ["/tmp/nexus_collector.py"])
recu = out.split()[0] if out else ""
if recu != attendu:
    sys.exit(f"  ✗ empreinte différente ({recu[:12]} ≠ {attendu[:12]}) — installation annulée")
print(f"  empreinte vérifiée : {attendu[:16]}…")

# 3. Installation + redémarrage du service
code, out, err = executer("/bin/sh", ["-c",
    "install -m 0755 /tmp/nexus_collector.py /opt/nexus-agent/nexus_collector.py "
    "&& rm -f /tmp/nexus_collector.py "
    "&& (systemctl restart nexus-collector.service 2>&1 || echo 'service absent') "
    "&& grep -oP 'VERSION_AGENT\\s*=\\s*\"\\K[^\"]+' /opt/nexus-agent/nexus_collector.py"])
print(f"  installation : code {code}")
if out.strip(): print("  " + out.strip().replace("\n", "\n  "))
if err.strip(): print("  stderr : " + err.strip()[:200])

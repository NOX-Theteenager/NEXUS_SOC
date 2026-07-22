# NEXUS SOC LAB — Troubleshooting

Pannes fréquentes rencontrées pendant l'installation OU pendant la démo,
avec commande de diagnostic + fix.

Tri par **fréquence décroissante** de mes observations sur ce projet.

---

## Pendant l'installation

### 1. `virt-install` : "error: no default network"

**Symptôme :** Impossible de créer une VM, message d'erreur libvirt.

**Diagnostic :**
```bash
virsh net-list --all
```

**Fix :**
```bash
sudo systemctl start libvirtd
virsh net-start default
virsh net-autostart default
```

---

### 2. Les VMs ne récupèrent pas leur IP fixe de VLAN

**Symptôme :** `ip a` dans vm-cible affiche une IP dynamique (ex. `10.42.10.15X`)
au lieu de `10.42.10.20`, ou aucune IP du tout.

**Cause :** La MAC de la VM ne correspond pas à la réservation DHCP, OU la VM
est branchée sur le mauvais bridge VLAN.

**Diagnostic :**
```bash
virsh dumpxml vm-cible | grep -E "mac|source network"
# doit afficher : mac address='52:54:00:aa:00:20'
#                 <source network='nexus-vlan10'/>
```

**Fix :** Éditer l'interface de la VM :
```bash
virsh edit vm-cible
# Corriger <mac address='...'/> et <source network='nexus-vlan10'/>
virsh destroy vm-cible && virsh start vm-cible
```

Rappel des associations (MAC / IP / VLAN) :
| VM        | MAC                 | IP           | Réseau       |
|-----------|---------------------|--------------|--------------|
| vm-cible  | 52:54:00:aa:00:20   | 10.42.10.20  | nexus-vlan10 |
| vm-dsi    | 52:54:00:aa:00:40   | 10.42.10.40  | nexus-vlan10 |
| vm-cibleB | 52:54:00:aa:00:50   | 10.42.20.20  | nexus-vlan20 |
| vm-kali   | 52:54:00:aa:00:30   | 10.42.30.30  | nexus-vlan30 |

---

### 3. Une VM ne joint pas le HÔTE SOC (10.42.0.1)

**Symptôme :** Depuis vm-cible, `curl http://10.42.0.1:8000/health` timeout,
alors que la VM a bien son IP de VLAN.

**Cause :** Le routage inter-VLAN (MikroTik) ou l'ACL vers mgmt n'est pas
configuré, OU ufw bloque virbr-mgmt côté hôte.

**Diagnostic :**
```bash
# Depuis la VM
ping -c 2 10.42.10.1     # gateway VLAN (MikroTik ether2) → doit répondre
ping -c 2 10.42.0.1      # HÔTE SOC → doit répondre si routage OK

# Sur le hôte
sudo ufw status | grep virbr-mgmt
```

**Fix :**
- Vérifier l'ACL MikroTik : `/ip firewall filter print` doit contenir la
  règle `dst-address=10.42.0.1 action=accept` (voir `03-gns3-architecture.md §5.2`)
- Côté hôte, ré-exécuter `scripts/host-configure.sh` (ajoute les règles ufw)

---

### 4. `mkcert -install` demande une confirmation graphique

**Symptôme :** Sur Ubuntu Desktop, `mkcert -install` ouvre une pop-up
`pkexec` pour ajouter le CA au trust store.

**Fix (headless) :**
```bash
sudo cp ~/.local/share/mkcert/rootCA.pem \
    /usr/local/share/ca-certificates/mkcert-nexus.crt
sudo update-ca-certificates
```

---

### 5. Un Cloud node GNS3 ne se connecte pas au bridge libvirt

**Symptôme :** Dans GNS3, le lien entre un Cloud node et le MikroTik est
"vert" mais les VMs du VLAN correspondant n'ont pas de connectivité.

**Cause :** Le Cloud node GNS3 n'est pas mappé sur le bon bridge libvirt,
ou le bridge n'existe pas encore.

**Diagnostic :**
```bash
# Sur le hôte : les 4 bridges doivent exister
ip -br link show | grep virbr-
# attendu : virbr-mgmt, virbr-vlan10, virbr-vlan20, virbr-vlan30
```

**Fix :**
- Si un bridge manque : relancer `./01-network-setup.sh`
- Dans GNS3 : clic-droit Cloud node → Configure → onglet Ethernet interfaces
  → cocher le bon `virbr-vlanXX` (voir `03-gns3-architecture.md §3.4`)

---

## Pendant la démo

### 6. `curl https://nexussoc.cm/health` renvoie 502

**Symptôme :** Le tunnel Cloudflare fonctionne mais uvicorn ne répond pas.

**Diagnostic sur le hôte :**
```bash
systemctl status nexus-soc | head -5
ss -tln | grep 8000
```

**Fix rapide :**
```bash
sudo systemctl restart nexus-soc
sleep 8
curl https://nexussoc.cm/health
```

---

### 7. Le mail Gmail OTP n'arrive pas dans les 30 secondes

**Symptôme :** Le POST /plg/register retourne 200 mais aucun mail reçu.

**Diagnostic :**
```bash
sudo journalctl -u nexus-soc --since "1 minute ago" | grep -iE "smtp|verify"
```

**Cause A : Gmail SMTP a rejeté l'auth (mot de passe d'app expiré)**

**Fix :** Recréer un mot de passe d'application Gmail →
https://myaccount.google.com/apppasswords → mettre à jour `.env` :
```bash
sed -i "s|^SMTP_PASSWORD=.*|SMTP_PASSWORD=xxxx yyyy zzzz aaaa|" .env
sudo systemctl restart nexus-soc
```

**Cause B : Gmail a mis le mail en spam**

Vérifier le dossier Spam de `nguetsajunior@gmail.com`.

**Fallback pendant la démo (< 30 s) :**
```bash
# Sur le HÔTE (qui est le SOC) — récupérer l'OTP directement en DB
docker exec nexus-postgres psql -U nexus -d nexus_soc \
    -tA -c "SELECT verification_otp FROM plg_registrations \
    WHERE email='DEMO_EMAIL@example.com' \
    ORDER BY verification_sent_at DESC LIMIT 1;"
```

Puis saisir cet OTP dans le formulaire. Dire : « pour la démo, j'affiche
l'OTP côté serveur — en production c'est bien envoyé par mail. »

---

### 8. Le portail DSI affiche "Erreur de connexion" après login

**Symptôme :** Login OK (JWT reçu) mais les données ne chargent pas.

**Cause probable :** CORS strict rejette les XHR car le navigateur envoie
`Origin: https://soc.nexus.local:8443` mais le backend n'autorise que
`https://nexussoc.cm`.

**Diagnostic :** Ouvrir console développeur Firefox (F12) → onglet
Console → chercher `CORS`.

**Fix :** Sur le HÔTE (les XHR du lab viennent de `soc.nexus.local:8443`,
il faut donc autoriser cette origine en plus de nexussoc.cm) :
```bash
sed -i "s|^NEXUS_CORS_ORIGINS=.*|NEXUS_CORS_ORIGINS=https://nexussoc.cm,https://soc.nexus.local:8443,https://portail.soc.nexus.local:8443|" \
    /home/noxtheteenager/Documents/Projets/NEXUS_SOC/.env
sudo systemctl restart nexus-soc
```

---

### 9. Firefox refuse le certificat `soc.nexus.local`

**Symptôme :** Écran "Cette connexion n'est pas sécurisée" dans Firefox
sur vm-dsi.

**Cause :** Le CA racine mkcert du HÔTE n'a pas été importé sur vm-dsi.

**Fix :**
```bash
# Sur le HÔTE (host-configure.sh a copié le CA dans ~/certs-lab/) :
scp ~/certs-lab/rootCA.pem dsi@10.42.10.40:/tmp/

# Sur vm-dsi :
sudo cp /tmp/rootCA.pem /usr/local/share/ca-certificates/nexus-mkcert.crt
sudo update-ca-certificates
# Redémarrer Firefox
```

Alternative rapide (accepte le certif à la main pour la démo) :
- Firefox → "Avancé" → "Accepter le risque et continuer"

---

### 10. `tcpdump` ne montre rien même quand on force du trafic

**Symptôme :** Pendant le scénario 1, le tcpdump n'affiche jamais de paquets
même quand on force du trafic ping.

**Cause :** L'utilisateur n'est pas root et tcpdump a besoin de CAP_NET_ADMIN,
ou on écoute le mauvais bridge.

**Fix :**
```bash
# Le trafic des VMs vers le SOC arrive sur virbr-mgmt (routé par MikroTik)
sudo tcpdump -nn -i virbr-mgmt ...
# Pour un VLAN précis : virbr-vlan10 / virbr-vlan20 / virbr-vlan30
```

---

### 11. La notification n'apparaît pas dans le portail DSI

**Symptôme :** Le scénario fraude UEBA passe, mais la cloche 🔔 reste vide.

**Diagnostic :**
```bash
# Sur le HÔTE (qui est le SOC) :
docker exec nexus-postgres psql -U nexus -d nexus_soc -tA -c \
    "SELECT COUNT(*) FROM notifications WHERE created_at > NOW() - INTERVAL '2 minutes';"
```

**Cause A : L'alerte a bien été créée mais la fonction PL/pgSQL
`emit_notification_from_alert()` n'a pas été appelée**

**Fix manuel :**
```sql
SELECT emit_notification_from_alert(id) FROM alerts
WHERE cree_le > NOW() - INTERVAL '5 minutes';
```

**Cause B : Le polling frontend est en pause**

Rafraîchir Firefox (F5) sur vm-dsi.

---

### 12. La VM vm-cible n'arrive pas à `nexus-emit`

**Symptôme :** `echo '{...}' | nexus-emit` retourne une erreur.

**Diagnostic :**
```bash
curl -v http://10.42.0.1:8000/ingest \
    -H "Authorization: Bearer $(cat /etc/nexus-agent/bearer)" \
    -H "Content-Type: application/json" -d '{"test":true}'
```

**Cause A :** Le bearer token n'est plus valide (agent supprimé côté admin)

**Fix :** Réenregistrer l'agent :
```bash
sudo /path/to/lab/scripts/vm-cible-setup.sh
```

**Cause B :** L'endpoint /ingest ne répond pas (backend down)

Voir panne #6.

---

### 13. Le scénario ransomware ne chiffre aucun fichier

**Symptôme :** Le script s'exécute mais 0 fichier .locked créé.

**Cause :** Les fichiers cible ont déjà été chiffrés lors d'une exécution
précédente ; ils n'ont plus l'extension .txt.

**Fix :**
```bash
sudo find /home/compta_agent -name "*.locked" -delete
sudo bash -c 'for i in {1..20}; do
    for dir in Rapports Mandats Budgets; do
        echo "Rapport N°$i - $(date -I)" \
            > /home/compta_agent/Documents/$dir/${dir,,}_$i.txt
    done
done'
sudo chown -R compta_agent:compta_agent /home/compta_agent/Documents
```

---

### 14. Le SOAR ne crée pas d'action "en attente"

**Symptôme :** Le playbook s'exécute mais toutes les actions sont
"SIMULÉE" ou "EXÉCUTÉE" — jamais "EN ATTENTE DE VALIDATION".

**Cause :** Le SOAR tourne en mode `dry-run` ou en mode `--execute` avec
`--high-override` bas.

**Fix :** Sur le HÔTE, vérifier les paramètres passés à SOAREngine :
```bash
cd /home/noxtheteenager/Documents/Projets/NEXUS_SOC
grep -n "SOAREngine(" Lot4_SOAR/soar_engine.py
# doit contenir : auto_exec_max_impact=MEDIUM, high_override=None
```

Pour la démo, lancer manuellement :
```bash
.venv/bin/python Lot4_SOAR/soar_engine.py --execute
```

---

### 15. Toutes les VMs ont perdu leur configuration après reboot

**Symptôme :** Après un reboot du hôte, tout est perdu — plus rien ne marche.

**Cause :** Les VMs ne sont pas configurées en `autostart`.

**Fix (à faire une fois pour toutes) :**
```bash
for vm in vm-cible vm-dsi vm-cibleB vm-kali; do
    virsh autostart "$vm"
done
# Et les 4 réseaux
for net in nexus-mgmt nexus-vlan10 nexus-vlan20 nexus-vlan30; do
    virsh net-autostart "$net"
done
```

Vérifier :
```bash
virsh list --all
# Colonne "State" doit être "running" après reboot
```

---

## Kit de survie : commandes à connaître par cœur

```bash
# Redémarrer tout le SOC
sudo systemctl restart nexus-soc caddy

# Voir les logs backend
sudo journalctl -u nexus-soc -f

# Voir les logs Caddy
sudo journalctl -u caddy -f

# Voir les containers Docker
docker ps

# Login CLI (utile pour tester)
TOKEN=$(curl -s http://127.0.0.1:8000/auth/token -X POST \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | jq -r .access_token)

# Faire un curl avec ce token
curl -s http://127.0.0.1:8000/admin/tenants -H "Authorization: Bearer $TOKEN" | jq

# Reset SQL rapide
docker exec nexus-postgres psql -U nexus -d nexus_soc -c "TRUNCATE alerts, notifications CASCADE;"

# Voir toutes les alertes récentes
docker exec nexus-postgres psql -U nexus -d nexus_soc -c \
    "SELECT id, type, entite, risque, cree_le FROM alerts ORDER BY cree_le DESC LIMIT 10;"
```

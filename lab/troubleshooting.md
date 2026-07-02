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

### 2. Les VMs ne récupèrent pas leur IP fixe

**Symptôme :** `ip a` dans vm-soc affiche une IP en `10.42.0.15X` (DHCP dynamique)
au lieu de `10.42.0.10`.

**Cause :** La MAC address de la VM ne correspond pas à la réservation DHCP.

**Diagnostic :**
```bash
virsh dumpxml vm-soc | grep mac
# doit afficher : mac address='52:54:00:aa:00:10'
```

**Fix :** Édit XML de la VM :
```bash
virsh edit vm-soc
# Changer <mac address='...'/> pour la valeur exacte du script 01
virsh destroy vm-soc && virsh start vm-soc
```

---

### 3. `docker: command not found` sur vm-soc après le script setup

**Symptôme :** Le script `vm-soc-setup.sh` a bien installé Docker, mais
`docker` n'est pas dans le PATH de l'utilisateur.

**Cause :** L'utilisateur `nexus` a été ajouté au groupe `docker`, mais
la session SSH courante n'a pas rechargé les groupes.

**Fix :**
```bash
exit                              # sortir du SSH
ssh nexus@10.42.0.10               # se reconnecter
groups                            # doit afficher : nexus adm sudo ... docker
docker ps                         # doit fonctionner sans sudo
```

Puis relancer le script setup, il détecte docker installé et passe à l'étape suivante.

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

### 5. Le script `vm-soc-setup.sh` échoue au step docker compose

**Symptôme :** `docker compose up` échoue avec "no configuration file provided".

**Cause :** Le chemin `Lot0_Socle/docker-compose.yml` n'existe pas — le
tarball du projet a été extrait dans un mauvais dossier.

**Diagnostic :**
```bash
ls ~/NEXUS_SOC/Lot0_Socle/docker-compose.yml
```

**Fix :** Retransférer le tarball depuis le hôte :
```bash
# Sur le hôte :
tar czf /tmp/nexus-soc.tar.gz -C ~/Documents/Projets NEXUS_SOC \
    --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='.env'
scp /tmp/nexus-soc.tar.gz nexus@10.42.0.10:/tmp/
# Sur vm-soc :
rm -rf ~/NEXUS_SOC
tar xzf /tmp/nexus-soc.tar.gz -C ~
```

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
# Récupérer l'OTP directement en DB
ssh nexus@10.42.0.10 'docker exec nexus-postgres psql -U nexus -d nexus_soc \
    -tA -c "SELECT verification_otp FROM plg_registrations \
    WHERE email='"'"'DEMO_EMAIL@example.com'"'"' \
    ORDER BY verification_sent_at DESC LIMIT 1;"'
```

Puis saisir cet OTP dans le formulaire. Dire : « pour la démo, j'affiche
l'OTP côté serveur — en production c'est bien envoyé par mail. »

---

### 8. Le portail DSI affiche "Erreur de connexion" après login

**Symptôme :** Login OK (JWT reçu) mais les données ne chargent pas.

**Cause probable :** CORS strict rejette les XHR car le navigateur envoie
`Origin: https://soc.minfi.local` mais le backend attend `https://nexussoc.cm`.

**Diagnostic :** Ouvrir console développeur Firefox (F12) → onglet
Console → chercher `CORS`.

**Fix :** Sur vm-soc :
```bash
sed -i "s|^NEXUS_CORS_ORIGINS=.*|NEXUS_CORS_ORIGINS=https://soc.minfi.local,https://portail.soc.minfi.local|" ~/NEXUS_SOC/.env
sudo systemctl restart nexus-soc
```

---

### 9. Firefox refuse le certificat `soc.minfi.local`

**Symptôme :** Écran "Cette connexion n'est pas sécurisée" dans Firefox
sur vm-dsi.

**Cause :** Le CA racine mkcert de vm-soc n'a pas été importé sur vm-dsi.

**Fix :**
```bash
# Sur vm-soc :
scp ~/.local/share/mkcert/rootCA.pem dsi@10.42.0.40:/tmp/

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

**Cause :** L'utilisateur n'est pas root et tcpdump a besoin de CAP_NET_ADMIN.

**Fix :**
```bash
sudo tcpdump -nn -i virbr-lab ...
```

---

### 11. La notification n'apparaît pas dans le portail DSI

**Symptôme :** Le scénario fraude UEBA passe, mais la cloche 🔔 reste vide.

**Diagnostic :**
```bash
# Sur vm-soc :
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
curl -v http://10.42.0.10:8000/ingest \
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

**Fix :** Sur vm-soc, vérifier les paramètres passés à SOAREngine :
```bash
grep -n "SOAREngine(" ~/NEXUS_SOC/Lot4_SOAR/soar_engine.py
# doit contenir : auto_exec_max_impact=MEDIUM, high_override=None
```

Pour la démo, lancer manuellement :
```bash
cd ~/NEXUS_SOC && .venv/bin/python Lot4_SOAR/soar_engine.py --execute
```

---

### 15. Toutes les VMs ont perdu leur configuration après reboot

**Symptôme :** Après un reboot du hôte, tout est perdu — plus rien ne marche.

**Cause :** Les VMs ne sont pas configurées en `autostart`.

**Fix (à faire une fois pour toutes) :**
```bash
for vm in vm-soc vm-cible vm-kali vm-dsi; do
    virsh autostart "$vm"
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
TOKEN=$(curl -s http://127.0.0.1:8000/auth/login -X POST \
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

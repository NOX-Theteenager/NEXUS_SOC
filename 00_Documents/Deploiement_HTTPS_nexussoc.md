# NEXUS SOC — Exposition HTTPS publique

Guide opérationnel pour rendre la plateforme accessible sur Internet avec un
certificat TLS valide et gratuit, **sans louer de VPS**, sans ouvrir de ports
sur le routeur, sans installer Nginx/Caddy.

Deux scénarios sont documentés :

1. **Quick tunnel** (`*.trycloudflare.com`) — démo/soutenance, immédiat, sans compte
2. **Tunnel nommé sur nexussoc.cm** — production, persistant, certificat reconnu

---

## Pré-requis communs

- Le serveur NEXUS SOC doit tourner localement : `uvicorn run:app --port 8000`
- Le binaire `cloudflared` est déjà téléchargé dans `.venv/bin/cloudflared`
- Le port `8000` doit être joignable en `localhost`

> Test rapide : `curl http://127.0.0.1:8000/health` doit répondre `{"status":"ok",...}`.

---

## Scénario 1 — Quick tunnel (démonstration immédiate)

Pour montrer le site à quelqu'un en 30 secondes, **sans compte Cloudflare** et
sans toucher au DNS. Le sous-domaine est aléatoire et expire au premier `Ctrl+C`.

```bash
cd /home/noxtheteenager/Documents/Projets/NEXUS_SOC
.venv/bin/cloudflared tunnel --url http://127.0.0.1:8000
```

Cloudflare imprime une URL du type :

```
https://sunrise-fact-book-constitutional.trycloudflare.com
```

Le site est immédiatement accessible en HTTPS depuis n'importe où, avec un
certificat TLS valide (chaîne Cloudflare). Idéal pour :

- Tester la PWA sur un téléphone tiers
- Faire une démo à un jury / un client sans avoir à partager son écran
- Vérifier le rendu mobile via des outils en ligne (PageSpeed, BrowserStack…)

**Limites** : sous-domaine éphémère, pas de SLA, pas de logs persistants. À ne
pas utiliser pour de la vraie production.

---

## Scénario 2 — Tunnel persistant sur **nexussoc.cm** (production)

C'est le mode recommandé maintenant que le domaine est acheté. Le résultat
final est `https://nexussoc.cm` avec un certificat **publiquement reconnu** par
tous les navigateurs (chaîne Cloudflare Origin), gratuit à vie, sans
renouvellement manuel, sans ouvrir de port sur le routeur de chez toi.

### Étape 1 — Ajouter nexussoc.cm à Cloudflare (5 min)

1. Aller sur <https://dash.cloudflare.com> et créer un compte gratuit
2. Cliquer **« Add a Site »**, saisir `nexussoc.cm`, sélectionner le plan **Free**
3. Cloudflare scanne les enregistrements DNS existants et propose deux **nameservers** Cloudflare (du type `xxx.ns.cloudflare.com`)
4. Aller chez le **registrar où le domaine a été acheté** et remplacer les nameservers par ceux de Cloudflare
5. Attendre la propagation DNS (de 15 minutes à 24 heures — généralement < 1 h)

> Vérification : `dig NS nexussoc.cm` doit lister les nameservers Cloudflare.

### Étape 2 — S'authentifier sur cloudflared

```bash
.venv/bin/cloudflared tunnel login
```

cloudflared ouvre un navigateur (ou affiche une URL à coller) → tu te connectes
à ton compte Cloudflare → tu **autorises le zone `nexussoc.cm`**. Un certificat
de tunnel est sauvegardé localement dans `~/.cloudflared/cert.pem`.

### Étape 3 — Créer le tunnel

```bash
.venv/bin/cloudflared tunnel create nexus-prod
```

Sortie : un **UUID** du tunnel + un fichier `~/.cloudflared/<UUID>.json`
(credentials du tunnel, à conserver précieusement).

### Étape 4 — Configurer le routage

Créer `~/.cloudflared/config.yml` :

```yaml
tunnel: nexus-prod
credentials-file: /home/noxtheteenager/.cloudflared/<UUID>.json

ingress:
  # racine + tout le frontend
  - hostname: nexussoc.cm
    service: http://127.0.0.1:8000
  # sous-domaine API si on veut le séparer plus tard
  - hostname: api.nexussoc.cm
    service: http://127.0.0.1:8000
  # règle catch-all obligatoire
  - service: http_status:404
```

### Étape 5 — Pointer le DNS de Cloudflare vers le tunnel

```bash
.venv/bin/cloudflared tunnel route dns nexus-prod nexussoc.cm
.venv/bin/cloudflared tunnel route dns nexus-prod api.nexussoc.cm
```

Ces commandes créent automatiquement des enregistrements `CNAME` proxifiés
dans Cloudflare. Plus rien à faire côté DNS.

### Étape 6 — Lancer le tunnel

```bash
.venv/bin/cloudflared tunnel run nexus-prod
```

Le site est maintenant accessible sur **https://nexussoc.cm**, avec un
certificat TLS reconnu par tous les navigateurs (chaîne Cloudflare Universal
SSL → renouvelée automatiquement, gratuite à vie).

### Étape 7 — Installer comme service systemd (pour démarrage auto)

```bash
sudo cp ~/.cloudflared/<UUID>.json /etc/cloudflared/
sudo cp ~/.cloudflared/config.yml /etc/cloudflared/

sudo .venv/bin/cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

À ce stade, même au redémarrage de la machine, le tunnel se rétablit
automatiquement et le site reste joignable.

---

## Sécurité production — recommandations complémentaires

Une fois le site exposé sur Internet, ces réglages deviennent indispensables :

### 1. Mettre à jour `NEXUS_CORS_ORIGINS`

```bash
export NEXUS_CORS_ORIGINS="https://nexussoc.cm,https://api.nexussoc.cm"
```

Sans ça, les XHR du frontend tomberont sur le rejet CORS strict du backend.

### 2. Forcer HTTPS au niveau Cloudflare

Dans le dashboard Cloudflare → **SSL/TLS → Edge Certificates** :
- ☑ **Always Use HTTPS**
- ☑ **HTTP Strict Transport Security (HSTS)** : enable, max-age 12 months

### 3. Activer la protection anti-bot Cloudflare

- **Security → Bots → Bot Fight Mode** : ON
- **Security → DDoS → HTTP DDoS Attack Protection** : Sensitivity = High

### 4. Restreindre l'accès aux pages internes (optionnel)

Cloudflare Access permet de mettre une **authentification SSO** devant
`/app/console.html` et `/app/portail.html` même avant que le frontend n'ait
chargé. Gratuit jusqu'à 50 utilisateurs.

### 5. Logs et surveillance

`cloudflared` envoie les logs vers stdout. En production :

```bash
sudo journalctl -u cloudflared -f
```

Le dashboard Cloudflare Analytics donne par défaut le trafic en temps réel
(requêtes/min, codes HTTP, géolocalisation).

---

## Comparaison rapide avec les alternatives

| Solution | Coût | TLS | Custom domain | Persistant | Effort |
|---|---|---|---|---|---|
| **Cloudflare Tunnel** *(retenu)* | gratuit | ✅ valide | ✅ | ✅ | faible |
| ngrok (gratuit) | gratuit | ✅ | ❌ URL aléatoire | ❌ | très faible |
| ngrok (paid) | ~10 $/mo | ✅ | ✅ | ✅ | très faible |
| VPS + Let's Encrypt + Caddy | ~5 €/mo | ✅ | ✅ | ✅ | moyen |
| localhost.run / serveo | gratuit | ✅ | ❌ | ❌ | très faible |

Cloudflare Tunnel gagne sur tous les critères pour le cas NEXUS SOC :
domaine acheté + souveraineté du serveur (la machine reste chez le client).

---

## Décommissionner le tunnel

```bash
sudo systemctl stop cloudflared
.venv/bin/cloudflared tunnel delete nexus-prod
```

Les enregistrements DNS créés par `route dns` restent et peuvent être
supprimés manuellement dans le dashboard Cloudflare DNS.

---

## Vérifications utiles

```bash
# Tunnel actif ?
.venv/bin/cloudflared tunnel list

# Le DNS de nexussoc.cm pointe-t-il vers Cloudflare ?
dig +short NS nexussoc.cm

# Certificat TLS valide ?
echo | openssl s_client -connect nexussoc.cm:443 -servername nexussoc.cm 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates

# Le frontend NEXUS SOC est-il bien servi ?
curl -sI https://nexussoc.cm/app/login.html | head -5
```

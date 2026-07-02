# NEXUS SOC — Configuration des services externes

Guide pas-à-pas pour brancher les trois services tiers utilisés par NEXUS SOC :

| Service        | Usage NEXUS SOC                                  | Plan recommandé      |
|----------------|--------------------------------------------------|----------------------|
| **Mailjet**    | E-mails transactionnels + codes OTP 6 chiffres   | Free (200 mails/jour)|
| **CinetPay**   | Pré-autorisation bancaire + paiement Mobile Money | Sandbox + Live       |
| **VirusTotal** | Enrichissement IOC (verdict multi-AV) dans le SOAR | Public API (gratuit) |

Toutes les clés sont stockées dans **`.env`** (à la racine du projet) — voir
[`/.env.example`](../.env.example) pour la liste complète des variables.

---

## 1. Mailjet — E-mails transactionnels & OTP

### 1.1 Création du compte

1. Aller sur <https://www.mailjet.com/signup> → **Sign up Free**
2. Choisir le plan **Free** (200 e-mails/jour, 6 000/mois — largement suffisant pour la démo et les premiers tenants)
3. Confirmer l'adresse e-mail de signup (Mailjet envoie un lien de validation)

### 1.2 Récupération des clés API

1. Une fois connecté : <https://app.mailjet.com/account/apikeys>
2. Copier les deux valeurs :
   - **API Key** (publique) → `MAILJET_API_KEY`
   - **Secret Key** (privée) → `MAILJET_API_SECRET`

```env
# Dans .env
MAILJET_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MAILJET_API_SECRET=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

### 1.3 Configuration de l'expéditeur

**Indispensable** : Mailjet refuse d'envoyer un e-mail tant que l'adresse `From`
n'est pas validée.

1. Dashboard Mailjet → **Senders & Domains** : <https://app.mailjet.com/account/sender>
2. Cliquer **Add a sender domain or address**
3. Deux options selon ce qui est disponible côté DNS :

   **Option A — Validation par e-mail (rapide, 2 minutes)**
   - Saisir une adresse précise (`no-reply@nexussoc.cm` par exemple)
   - Mailjet envoie un mail à cette adresse avec un lien de confirmation
   - Cliquer le lien → expéditeur validé

   **Option B — Validation par domaine (recommandé prod)**
   - Saisir le domaine complet (`nexussoc.cm`)
   - Mailjet fournit **3 enregistrements DNS** à ajouter chez le registrar (ou
     dans Cloudflare DNS) :
     | Type | Nom | Valeur |
     |------|-----|--------|
     | TXT  | `nexussoc.cm` | `v=spf1 include:spf.mailjet.com ?all` |
     | TXT  | `mailjet._domainkey.nexussoc.cm` | `<long_dkim_key>` |
     | TXT  | `_dmarc.nexussoc.cm` | `v=DMARC1; p=none; rua=mailto:postmaster@nexussoc.cm` |
   - Après propagation DNS (5–60 min), revenir et cliquer **Verify domain**
   - Une fois validé, **toutes** les adresses `@nexussoc.cm` peuvent être expéditrices

```env
# Dans .env (après validation)
MAILJET_FROM_EMAIL=no-reply@nexussoc.cm
MAILJET_FROM_NAME=NEXUS SOC
```

### 1.4 Choix du mode

```env
# log     → aucun appel HTTP, on logge le destinataire et le sujet (idéal dev)
# sandbox → l'API valide la requête mais n'envoie aucun e-mail (test sans bruler le quota)
# live    → envoi réel
MAILJET_MODE=live
```

### 1.5 Test rapide depuis la ligne de commande

```bash
.venv/bin/python -c "
import os; os.environ['MAILJET_MODE'] = 'live'
import sys; sys.path.insert(0, 'Lot1_Agent_Go')
from mailjet_client import send_otp_email
print(send_otp_email('votre.adresse@example.com', '123456', 'vérification'))
"
```

Attendu : `{'ok': True, 'mode': 'live', 'message_id': '...'}` et un e-mail
reçu en quelques secondes.

### 1.6 Suivi des envois

Dashboard → **Statistics** : taux de délivrabilité, bounces, plaintes spam.
La free tier garde 6 mois d'historique.

---

## 2. CinetPay — Paiement Mobile Money & carte bancaire

### 2.1 Création du compte marchand

1. Aller sur <https://admin.cinetpay.com/login> → **Créer un compte**
2. Renseigner les informations du marchand :
   - **Type** : Entreprise (ou particulier pour la phase de test)
   - **Nom commercial** : `NEXUS SOC`
   - **Pays** : Cameroun
   - **Secteur** : Logiciel / SaaS
3. CinetPay demande des justificatifs (RCCM, NIU pour passer en mode live) →
   peut prendre 24–72 h. **La sandbox est disponible immédiatement.**

### 2.2 Récupération des clés API

1. Connexion → **Intégration** → **Clés API** : <https://admin.cinetpay.com/integration/apikey>
2. Onglet **Sandbox** d'abord (pour tester sans vrai argent) :
   - **API Key** → `CINETPAY_API_KEY`
   - **Site ID** → `CINETPAY_SITE_ID`
   - **Secret Key** → `CINETPAY_SECRET_KEY` (utilisée pour vérifier la signature des webhooks)
3. Onglet **Production** une fois le compte validé : mêmes champs, valeurs différentes

```env
# .env — environnement sandbox
CINETPAY_API_KEY=12345678abcdef
CINETPAY_SITE_ID=987654
CINETPAY_SECRET_KEY=zzzzzzzzzzzzzzz
CINETPAY_CURRENCY=XAF              # FCFA pour le Cameroun
CINETPAY_MODE=sandbox              # ou "live" / "stub"
```

### 2.3 Configuration des URL de notification & retour

CinetPay a besoin de **deux URL publiquement joignables en HTTPS** :

- **`notify_url`** — webhook serveur-à-serveur que CinetPay appelle quand le
  paiement change d'état. **C'est elle qui fait foi**, pas le retour client.
- **`return_url`** — URL où l'utilisateur est redirigé après paiement (succès
  ou échec).

```env
# .env (via Cloudflare Tunnel : https://nexussoc.cm)
CINETPAY_NOTIFY_URL=https://nexussoc.cm/plg/cinetpay/notify
CINETPAY_RETURN_URL=https://nexussoc.cm/app/landing.html#paiement-confirme
```

Côté dashboard CinetPay → **Intégration** → **Notification** :
- Coller exactement les mêmes URL
- Méthode HTTP : **POST**
- Signature : **HMAC-SHA256** activée (CinetPay envoie le header `X-Token` que
  NEXUS SOC vérifie via `cinetpay_client.verify_webhook_signature()`)

### 2.4 Canaux de paiement à activer

Dashboard → **Intégration** → **Paramètres** → **Modes de paiement** :

| Canal | Couverture Cameroun | Activer |
|-------|---------------------|---------|
| Orange Money Cameroun | ✓ | ✅ |
| MTN Mobile Money Cameroun | ✓ | ✅ |
| Express Union Mobile | ✓ | ✅ |
| Visa / Mastercard | International | ✅ |
| Wave | Sénégal uniquement | ❌ |

NEXUS SOC utilise `"channels": "ALL"` dans son `init_payment()` → CinetPay
propose à l'utilisateur la liste des canaux activés sur le marchand.

### 2.5 Test en sandbox

CinetPay fournit des **numéros de test** pour Orange Money / MTN MoMo sans
mouvement réel d'argent :

| Canal | Numéro test | OTP test |
|-------|-------------|----------|
| Orange Money CM | `699000000` | `1234` |
| MTN MoMo CM | `670000000` | `1234` |
| Visa | `4111 1111 1111 1111` | CVV `123`, exp `12/25` |

Commande de test bout-en-bout :

```bash
.venv/bin/python -c "
import os, sys
sys.path.insert(0, 'Lot8_PLG')
from cinetpay_client import init_payment
print(init_payment(100, 'Test NEXUS SOC', 'test@nexussoc.cm'))
"
```

Attendu (en sandbox) :
```json
{
  "success": true,
  "transaction_id": "NEXUS-...",
  "payment_url": "https://checkout.cinetpay.com/payment/abc123",
  "message": "Initialisation OK"
}
```

### 2.6 Passage en production

Une fois le compte marchand validé par CinetPay :

1. Remplacer `CINETPAY_API_KEY` / `CINETPAY_SITE_ID` / `CINETPAY_SECRET_KEY`
   par les clés de l'onglet **Production**
2. `CINETPAY_MODE=live`
3. Activer les canaux de paiement définitifs côté dashboard
4. Vérifier que `CINETPAY_NOTIFY_URL` répond bien `200 OK` en POST :
   ```bash
   curl -X POST -H "Content-Type: application/json" -d '{}' \
        https://nexussoc.cm/plg/cinetpay/notify
   ```

### 2.7 Diagnostic du webhook

Dashboard CinetPay → **Transactions** → cliquer sur une transaction → onglet
**Notifications** : journal des appels HTTP que CinetPay a faits sur la
`notify_url`, avec code de retour et corps reçu.

Si le webhook échoue (401, 5xx) :
- 401 = signature `X-Token` invalide → `CINETPAY_SECRET_KEY` mal configurée
- 5xx = erreur côté NEXUS SOC → consulter `journalctl -u nexus-soc` (ou logs uvicorn)

---

## 3. VirusTotal — Enrichissement IOC dans le SOAR

### 3.1 Création du compte & récupération de la clé

1. Aller sur <https://www.virustotal.com/gui/join-us> → créer un compte gratuit
2. Confirmer l'adresse e-mail
3. Aller sur <https://www.virustotal.com/gui/my-apikey>
4. Copier la **Public API Key** affichée (64 caractères hexadécimaux)

```env
# .env
VIRUSTOTAL_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
VIRUSTOTAL_ENABLED=true
VIRUSTOTAL_CACHE_HOURS=24    # cache local pour éviter le rate-limit
```

### 3.2 Quotas et limites

La clé publique gratuite est limitée à :
- **4 requêtes / minute**
- **500 requêtes / jour**
- **15 500 requêtes / mois**

NEXUS SOC respecte ces limites en :
1. **Cachant** chaque verdict pendant `VIRUSTOTAL_CACHE_HOURS` (24 h par défaut)
   → un IOC vu deux fois dans la journée n'est pas recompté.
2. **Limitant** à 5 IOC max par alerte (les plus pertinents extraits par
   regex de l'entité et des `reasons`).
3. **Désactivation à chaud** possible via `VIRUSTOTAL_ENABLED=false` sans
   redémarrer (lu à chaque appel).

### 3.3 Intégration dans les playbooks SOAR

Le connecteur `enrich_ioc` est désormais en tête des 4 playbooks
([`Lot4_SOAR/soar_engine.py`](../Lot4_SOAR/soar_engine.py)) :

```python
PLAYBOOKS = {
    "Fraude interne":        ["enrich_ioc", "journal_investigation", "notify_dsi", ...],
    "Exfiltration":          ["enrich_ioc", "journal_investigation", "freeze_account", ...],
    "Ransomware":            ["enrich_ioc", "snapshot_memory", "isolate_host", ...],
    "Anomalie réseau / C2":  ["enrich_ioc", "journal_investigation", "block_ip", ...],
}
```

Pour chaque alerte, NEXUS SOC :
1. Extrait les IP, hashes et domaines présents dans `alert.entity` et `alert.reasons`
2. Interroge VirusTotal pour chacun (4 req/min max)
3. Pour les verdicts `malveillant` ou `suspect`, **ajoute la mention au rapport DSI**
4. Cache le résultat 24 h dans la RAM du process

### 3.4 Test rapide

```bash
.venv/bin/python -c "
import os; os.environ['VIRUSTOTAL_ENABLED'] = 'true'
import sys; sys.path.insert(0, 'Lot4_SOAR')
from virustotal_client import lookup
print(lookup('8.8.8.8'))            # Google DNS → propre
print(lookup('45.155.205.233'))     # IP connue malveillante
"
```

Attendu :
```json
{"ioc": "8.8.8.8", "verdict": "propre", "malicious": 0, ...}
{"ioc": "45.155.205.233", "verdict": "malveillant", "malicious": 15, ...}
```

### 3.5 Plan payant (perspective)

Si NEXUS SOC dépasse 500 IOC/jour (≈ 5 tenants actifs avec ~100 alertes/jour) :
- **VT Intelligence** : 999 USD/mois — 1 000 req/min, historique 90 jours
- **VT Enterprise** : sur devis — quotas élevés, accès aux outils de hunting

Pour le périmètre stage MINFI + 3 microfinances de démo, la clé publique
gratuite suffit largement (cache 24 h → ~50 lookups uniques/jour).

---

## 4. Récapitulatif du fichier `.env` à compléter

Une fois les trois comptes créés, voici la section "services externes" du
fichier `.env` à compléter (le reste vient déjà de `.env.example`) :

```env
# ── Mailjet ──────────────────────────────────────────────────────────────────
MAILJET_API_KEY=
MAILJET_API_SECRET=
MAILJET_FROM_EMAIL=no-reply@nexussoc.cm
MAILJET_FROM_NAME=NEXUS SOC
MAILJET_MODE=live                  # log | sandbox | live
OTP_TTL_S=300

# ── CinetPay ─────────────────────────────────────────────────────────────────
CINETPAY_API_KEY=
CINETPAY_SITE_ID=
CINETPAY_SECRET_KEY=
CINETPAY_CURRENCY=XAF
CINETPAY_MODE=sandbox              # stub | sandbox | live
CINETPAY_NOTIFY_URL=https://nexussoc.cm/plg/cinetpay/notify
CINETPAY_RETURN_URL=https://nexussoc.cm/app/landing.html#paiement-confirme

# ── VirusTotal ───────────────────────────────────────────────────────────────
VIRUSTOTAL_API_KEY=
VIRUSTOTAL_ENABLED=true
VIRUSTOTAL_CACHE_HOURS=24
```

Après modification, **redémarrer uvicorn** (les variables sont lues au boot
par `dotenv.load_dotenv()` dans [`run.py`](../run.py)).

---

## 5. Validation de l'intégration complète

Une fois les trois services configurés en mode `live` / `sandbox` :

```bash
# 1. Activer .venv et lancer l'API
.venv/bin/uvicorn run:app --host 0.0.0.0 --port 8000

# 2. Tester l'inscription PLG (envoie un e-mail OTP via Mailjet)
curl -X POST http://localhost:8000/plg/register \
  -H "Content-Type: application/json" \
  -d '{"email":"votre@email.com","organization_name":"Test","sector":"microfinance"}'

# 3. Vérifier l'OTP reçu
curl -X POST http://localhost:8000/plg/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"email":"votre@email.com","otp":"123456"}'

# 4. Lancer la pré-autorisation CinetPay (sandbox)
curl -X POST http://localhost:8000/plg/preauth \
  -H "Content-Type: application/json" \
  -d '{"registration_id":"<uuid>","card_token":"sandbox_ok"}'

# 5. Vérifier l'enrichissement VirusTotal sur le SOAR
.venv/bin/python Lot4_SOAR/soar_engine.py
# (le 1er pas du playbook affichera un enrichissement VirusTotal)
```

Si tout passe ✓, NEXUS SOC est prêt à recevoir de vrais utilisateurs.

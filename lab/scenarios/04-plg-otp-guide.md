# Scénario 4 — Inscription PLG SaaS avec OTP Gmail réel

## Objectif de la démo

Démontrer qu'une microfinance camerounaise peut, **en 3 minutes chrono** et
**sans intervention commerciale**, activer un compte NEXUS SOC gratuit
depuis Internet, via l'URL publique `https://nexussoc.cm`.

C'est le canal SaaS complémentaire au déploiement souverain montré dans
les 3 autres scénarios.

## Où ça se joue

**Depuis le poste hôte** Ubuntu (le PC de démo), avec Firefox — PAS depuis
les VMs. Les VMs du lab sont en réseau isolé sans Internet ; le PLG SaaS
nécessite Internet réel.

## Préparation (avant la démo)

1. Sur le hôte, vérifier que le tunnel Cloudflare est up :

   ```bash
   curl -sI https://nexussoc.cm/health | head -3
   # attendu : HTTP/2 200
   ```

2. Ouvrir Firefox et **avoir Gmail déjà connecté** dans un onglet
   (`nguetsajunior@gmail.com`) — pour que le mail arrive visiblement
   en 5 secondes.

3. Ouvrir un terminal côté hôte pour montrer les logs en direct
   (le HÔTE est le serveur SOC + PLG public via cloudflared) :

   ```bash
   sudo journalctl -u nexus-soc -f | grep -iE "PLG verify|SMTP"
   ```

   (Le PLG public tourne sur le hôte, exposé via nexussoc.cm. Ce
   scénario tourne uniquement contre `nexussoc.cm`.)

## Déroulé de la démo (~6 min)

### Étape 1 — Landing (1 min)

- Ouvrir un nouvel onglet Firefox → **`https://nexussoc.cm`**
- Montrer :
  - Le hero animé 3D
  - Le CTA « Essai gratuit 30 jours »
  - Le pricing en FCFA (Starter 25 000, Business 75 000, Enterprise 200 000)

**Dialogue possible :**
> « Voici la landing publique. Une DSI qui cherche un SOC pour sa microfinance
> arrive ici, comprend la valeur en 30 secondes, clique sur "Essai gratuit". »

### Étape 2 — Formulaire d'inscription (1 min)

- Cliquer sur « Essai gratuit »
- Remplir :
  - E-mail : **une adresse Gmail que le jury peut vérifier** (idéal : demander à un juré son mail, ou utiliser ton mail secondaire et projeter Gmail sur écran)
  - Organisation : `Microfinance Démo Jury`
  - Secteur : `Microfinance`
- Cliquer « Créer mon compte »

**Dialogue :**
> « Notre code refuse deux catégories : les e-mails jetables
> (mailinator, yopmail) et les domaines gouvernementaux (.gov.cm, .minfi.gov.cm)
> qui sont redirigés vers le canal souverain. »

### Étape 3 — OTP arrive en direct (2 min)

- Basculer sur l'onglet Gmail
- **En moins de 10 secondes**, le mail arrive
- Ouvrir le mail → sujet : « NEXUS SOC — Confirmez votre adresse... »
- Montrer :
  - Le code OTP à 6 chiffres (grand, lisible)
  - Le lien « Activer mon compte » alternatif
- Revenir à l'onglet NEXUS SOC → saisir le code → validation

**Dialogue :**
> « L'OTP est envoyé via SMTP Gmail avec un compte NEXUS SOC dédié.
> En production, on utilisera un domaine authentifié `no-reply@nexussoc.cm`
> avec SPF/DKIM/DMARC ; pour la démo, on utilise directement Gmail. »

### Étape 4 — Pré-autorisation CinetPay (1 min)

- Le formulaire demande la CB / mobile money
- Saisir un token de démo (sandbox) : `sandbox_ok` OU utiliser le numéro
  de test Orange Money `699000000` avec OTP `1234`
- Validation

**Dialogue :**
> « À ce stade, on demande une pré-autorisation à 100 FCFA (immédiatement
> remboursée) via CinetPay. Objectif : filtrer les inscriptions frauduleuses
> qui pourraient saturer le cluster Kafka. Payer 100 FCFA prouve qu'on est
> une vraie organisation, pas un bot. »

### Étape 5 — Console fournie (1 min)

- Après activation → dashboard tenant qui affiche :
  - Tenant ID
  - Essai 30 jours restants
  - Quota agents : 0/5
  - Quota événements : 0/10 000/jour
- Bouton « Télécharger l'agent Windows/Linux »

**Dialogue :**
> « Trois minutes chrono depuis la landing. La microfinance a maintenant
> son tenant isolé (row-level security en PostgreSQL), peut télécharger
> l'agent NEXUS, et l'installer sur ses 5 postes en essai gratuit.
> Aucune force de vente n'a été mobilisée : c'est du PLG pur. »

## Preuves à collecter pour le mémoire

- Screenshot de l'e-mail OTP reçu (avec timestamp visible)
- Log terminal : `PLG verify | backend=smtp | mode=live | ok=True`
- Screenshot du dashboard tenant post-activation
- Enregistrement d'écran (OBS) des 6 minutes complètes

## Points de vigilance

- **Ne pas utiliser une adresse @minfi.cm** : le code va la rejeter avec
  redirection "Contact souverain" (comportement voulu, mais mauvaise démo).
- **Vérifier que Gmail SMTP fonctionne** avant la soutenance :

  ```bash
  cd ~/Documents/Projets/NEXUS_SOC
  .venv/bin/python -c "
  from dotenv import load_dotenv; load_dotenv()
  import sys; sys.path.insert(0, 'Lot1_Agent_Go')
  from smtp_client import send_otp_email
  print(send_otp_email('nguetsajunior@gmail.com', '999999', 'test avant soutenance'))
  "
  # doit retourner {'ok': True, 'mode': 'live', ...}
  ```

- **Si le mail n'arrive pas** en 30 secondes : basculer manuellement le
  compte en verified via SQL, en expliquant que "on utilise le lien magique
  à la place du code". Faire une deuxième prise si possible.

  ```bash
  # Fallback : marque le compte comme verifié à la main
  ssh nexus@nexussoc.cm  # ou sur le hôte directement
  psql -U nexus -d nexus_soc -c "
    UPDATE plg_registrations
    SET email_verified = TRUE
    WHERE email = 'DEMO_EMAIL@example.com';
  "
  ```

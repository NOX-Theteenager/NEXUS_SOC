# NEXUS SOC — Restitution : portail + LLM Analyst + notifications (Lot 5)

La **couche de restitution** transforme les incidents techniques (issus de la corrélation SIEM
et des modèles d'IA) en quelque chose qu'un **DSI non-technicien** comprend et exploite : un
**portail web** clair, des **explications en langage naturel** générées par le LLM Analyst, des
**notifications SMS** en temps réel et un **rapport WhatsApp hebdomadaire** de synthèse.

> ✳ **Tout est bilingue FR / EN** selon la préférence de l'utilisateur. Le portail bascule en
> direct ; les SMS, le rapport WhatsApp et les explications de l'Analyst sont rendus dans la
> langue choisie.

---

## 1. Contenu

| Fichier | Rôle |
|---|---|
| `portal/index.html` | Portail web bilingue (mode sombre, ops center) — s'ouvre dans un navigateur |
| `portal/preview_fr.png`, `preview_en.png` | Captures du portail FR et EN |
| `notifier.py` | LLM Analyst + générateurs SMS et rapport WhatsApp, bilingues |
| `out_lot5/explanation_{fr,en}.txt` | Explications de l'Analyst pour l'incident corrélé |
| `out_lot5/sms_{fr,en}.txt` | Notifications SMS générées |
| `out_lot5/whatsapp_{fr,en}.txt` | Rapport WhatsApp hebdomadaire généré |

## 2. Le portail

Ouverture directe dans un navigateur :

```bash
xdg-open portal/index.html   # Linux
open portal/index.html       # macOS
```

Aucun build ni serveur n'est requis — c'est un fichier HTML autonome (CSS et JS embarqués,
polices via Google Fonts). Pour servir le portail depuis la plateforme en production, on le
déposera derrière un reverse-proxy (Nginx) du socle, alimenté par des endpoints de l'API
`scoring-service` (incidents, alertes, notifications).

**Éléments signature** :
- **Timeline kill-chain** colorée par tactique MITRE — l'incident reconstitué se lit d'un coup
  d'œil (Initial Access → Execution → Collection → C2 → Impact).
- **Citation de l'Analyst** en serif italique (Fraunces) : l'explication en langage naturel
  est traitée comme une analyse éditoriale, pas comme un log technique.
- **Typographie** : Fraunces (display, italiques d'emphase), Manrope (corps), JetBrains Mono
  (champs techniques : timestamps, MITRE IDs, hôtes).
- **i18n** : un bouton FR/EN dans le header. La fonction `setLang()` parcourt tous les éléments
  `[data-i18n]` (clé → dictionnaire `STRINGS`) et `[data-fr][data-en]` (contenu inline bilingue).

## 3. Le LLM Analyst

Une classe `LLMAnalyst` avec **deux modes** :

- **`template`** (par défaut) — explications déterministes basées sur des modèles bilingues.
  Toujours disponible, rapide, sans hallucination ni coût. Sert aussi de **filet de sécurité**
  lorsque le LLM est indisponible.
- **`llm`** — délègue à un Mistral / Llama via une API compatible OpenAI (Ollama, vLLM…).
  Activé par les variables `LLM_API_URL` et `LLM_MODEL`.

L'entrée est un **incident structuré** (type, hôte, risque, tactiques, techniques MITRE, chaîne,
hors heures…). La sortie est un paragraphe de 3 à 5 phrases factuelles, dans la langue choisie.

**Exemple FR** (généré sur l'incident corrélé du Lot 2) :

> « Le système a détecté un incident de type « rançongiciel » sur l'hôte POSTE-COMPTA-07.
> L'incident reconstitue une chaîne d'attaque en 6 étapes (accès initial, exécution, collecte,
> commande et contrôle, impact), cartographiée sur MITRE ATT&CK (T1005, T1059, T1071, T1204,
> T1486). L'activité s'est déroulée en dehors des heures ouvrables, ce qui renforce le caractère
> suspect. Le score de risque atteint 100/100. Le poste a été isolé du réseau et une capture
> mémoire a été réalisée pour enquête. »

## 4. Notifications

### SMS — alerte temps réel

Courte (≤ 160 caractères), envoyée dès qu'un incident critique se produit. Génération via
`build_sms(incident, lang)`.

- FR : `🚨 NEXUS SOC — Rançongiciel sur POSTE-COMPTA-07 · risque 100/100. Action : isoler. Détails : nexussoc.cm/i/abc123`
- EN : `🚨 NEXUS SOC — Ransomware on POSTE-COMPTA-07 · risk 100/100. Action: isolate. Details: nexussoc.cm/i/abc123`

L'envoi (`send_sms`) est ici **simulé**. En production, on branche un connecteur Twilio ou une
passerelle SMS locale (Orange / MTN via accord opérateur).

### Rapport WhatsApp hebdomadaire

Synthèse hebdomadaire envoyée au DSI tous les lundis matin. Génération via
`build_whatsapp_weekly(stats, lang)`. Contenu : score de sécurité + delta, événements de la
semaine, action requise, conseil de la semaine, lien vers le rapport complet.

> ⚠ **Contrainte WhatsApp Business API** : en production, les messages envoyés hors de la
> fenêtre de 24 h doivent suivre un **template approuvé par Meta**. Le code fournit le corps du
> message ; au déploiement, il faudra le décliner en template Meta (avec variables dynamiques)
> et obtenir l'approbation. Les SMS, eux, n'ont pas cette contrainte.

## 5. Exécution

```bash
# Génère explications + SMS + rapport WhatsApp à partir d'un incident corrélé
python notifier.py --incident ../pipeline/out_lot2/correlated_incidents.json --out ./out_lot5

# Avec un LLM réel (Mistral via Ollama, par exemple) :
export LLM_API_URL=http://localhost:11434/v1/chat/completions
export LLM_MODEL=mistral
python notifier.py
```

## 6. Place dans NEXUS SOC

```
Corrélation SIEM + Modèles IA → incident structuré
   → LLM Analyst (explication FR ou EN)
   → Portail (carte d'incident + citation)
   → SMS (alerte temps réel)
   → WhatsApp (rapport hebdomadaire)
```

Le portail consommera en production des endpoints du `scoring-service` (alertes, incidents,
historique des notifications) ; les langues seront déterminées par la préférence stockée dans
la table `users` (PostgreSQL).

## 7. Pistes (chapitre perspectives)

- Brancher un vrai LLM local (Mistral 7B via Ollama) et comparer aux explications template
  (qualité, longueur, latence, coût).
- Authentification SSO (OIDC) sur le portail ; rôles RBAC (admin plateforme, analyste SOC, DSI,
  lecteur) déjà modélisés dans le schéma SQL du Lot 0.
- File d'approbation visible dans le portail (workflow human-in-the-loop pour les actions à fort
  impact du SOAR).
- Templates WhatsApp officiellement approuvés par Meta (procédure à anticiper pour le
  déploiement production).
- Localisation supplémentaire (autres langues nationales) — l'infrastructure i18n est en place.

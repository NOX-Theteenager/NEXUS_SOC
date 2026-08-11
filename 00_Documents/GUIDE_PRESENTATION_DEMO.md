# NEXUS SOC — Guide de présentation et de démonstration

Ce document explique **comment présenter la plateforme**, **qui voit quoi**, et
donne le **déroulé exact d'une démonstration live** (soutenance ou revue avec les
intervenants du CENADI). Il distingue clairement ce qui est **réellement mesuré**
de ce qui reste **synthétique**, pour tenir un discours honnête devant un jury.

---

## 1. En une phrase

NEXUS SOC est une plateforme SOC **open source et souveraine**, exploitée en
interne par le CENADI, qui **collecte de la télémétrie réelle** sur les systèmes
supervisés (SIGIPES, ANTILOPE, réseau interne), la **score par IA**, **lève des
alertes**, propose une **réponse SOAR** encadrée, et **visualise le tout** —
sans qu'aucune donnée ne quitte le datacenter.

---

## 2. Réel vs synthétique — à assumer devant le jury

C'est le point de crédibilité le plus important. Sois précis :

| Élément | Statut | À dire |
|---|---|---|
| Collecte de télémétrie (agent) | **Réel** | Compteurs TCP du noyau (`ss`), sessions, accès fichiers sensibles — mesurés, pas inventés. |
| Chaîne ingestion → Kafka → scoring → alerte → SOAR | **Réel** | Signée HMAC, fonctionne de bout en bout. |
| Métriques de supervision (séries temporelles) | **Réel** | Table `metrics` alimentée en continu, visibles dans l'onglet Supervision. |
| Isolation par périmètre (RLS) | **Réel** | Vérifiée : un périmètre ne voit pas les autres. |
| Seuils de risque | **Recalibrés sur base réelle** | Réglés sur la distribution réelle de la machine (99e percentile). |
| Détection de fraude (Modèle 2 UEBA) | **Fonctionnel** | Discrimine : activité normale → 0, exfiltration → 100 + alerte. |
| Détection réseau (Modèle 1) | **Limité** | Entraîné sur CICFlowMeter ; alimenté ici par une approximation `ss`. À alimenter par une vraie sonde de flux (NetFlow) dans le lab. |
| Métriques ROC-AUC 0,987 / 0,969 | **Synthétique** | Obtenues sur données CICIDS/CERT synthétiques. Ordres de grandeur, pas preuve terrain (limite R1 documentée). |
| Connecteurs SOAR (gel compte, isolation) | **Simulés** | Le moteur et les garde-fous sont réels ; les connecteurs sont à brancher sur l'AD/pare-feu du CENADI. |

**Formule pour le jury :** « Les *métriques plateforme* (débits, MTTD, alertes,
supervision) sont réellement mesurées. Les *métriques modèle* (AUC) sont des
ordres de grandeur sur données synthétiques, tant que je n'ai pas de journaux
SIGIPES/ANTILOPE réels et étiquetés. »

---

## 3. Les intervenants et leurs vues (qui voit quoi)

Point d'entrée unique : **`https://nexussoc.cm`** (ou `http://<SOC>:8000` en lab).
La racine redirige vers la connexion.

| Intervenant | Rôle | Compte (démo, mdp `admin`) | Ce qu'il voit |
|---|---|---|---|
| **Opérateur CENADI** | `admin_plateforme` | `admin@nexussoc.cm` | Console complète : périmètres, agents, santé, **Supervision (métriques)**, + tout l'analyste. |
| **Analyste SOC CENADI** | `analyste_soc` | `soc@nexussoc.cm` | File d'alertes **tous périmètres**, approbation SOAR, tableau de bord SOC. |
| **Responsable de périmètre** | `dsi_client` | `resp.sigipes@cenadi.cm`, `resp.antilope@cenadi.cm` | Portail filtré : **uniquement son périmètre** (RLS) — alertes, agents, notifications, rapports. |

> En soutenance, ouvre **deux onglets** : la **console opérateur** (vue globale)
> et un **portail de périmètre** (vue restreinte) → tu démontres visuellement
> l'isolation.

---

## 4. Vérifier que tout tourne (avant la démo)

```bash
# Services
systemctl is-active nexus-soc nexus-postgres        # actifs
docker ps --format '{{.Names}}\t{{.Status}}'        # nexus-postgres, nexus-kafka (, wazuh…)

# Santé applicative
curl -s http://127.0.0.1:8000/health/detailed | python3 -m json.tool
#   attendu : status "ok", kafka ok, m1=true, m2=true

# Collecteur de télémétrie réelle en marche (métriques dynamiques)
systemctl is-active nexus-collector   # si installé en service
#   sinon : python3 Lot1_Agent_Go/nexus_collector.py --loop --interval 30 &
```

Si `/health` n'est pas « ok » : voir §8 (Wazuh optionnel) — la détection IA
fonctionne même sans Wazuh.

---

## 5. Déroulé de la démonstration live (~10 min)

### Acte 1 — La plateforme et la supervision réelle (2 min)
1. Connexion `admin@nexussoc.cm` → **console opérateur**.
2. Onglet **Périmètres** : SIGIPES, ANTILOPE, Réseau/LAN CENADI (criticités).
3. Onglet **Supervision** : montre les **courbes réelles** (risque réseau, risque
   UEBA, événements ingérés). Insiste : « ce sont de vraies mesures, mises à jour
   en continu par les agents ». Change la plage (1 h / 24 h).

### Acte 2 — L'isolation par périmètre (1 min)
4. Nouvel onglet privé → connexion `resp.sigipes@cenadi.cm` → **portail**.
5. Montre qu'il **ne voit que SIGIPES**. « Le responsable ANTILOPE ne verrait
   qu'ANTILOPE. C'est la Row-Level Security de PostgreSQL. »

### Acte 3 — Une attaque détectée en direct (4 min)
6. Depuis la VM surveillée (ou le poste SOC) :
   ```bash
   python3 Lot1_Agent_Go/nexus_collector.py --simulate exfil
   ```
   (En lab, depuis vm-app-gov : `sudo bash scenarios/03-exfiltration-solde.sh`.)
7. Reviens sur la **console → File d'alertes** : l'alerte **Fraude interne,
   risque 100** apparaît (rafraîchissement auto ~30 s, ou bouton ↻).
8. Onglet **Supervision** : la courbe **risque UEBA monte à 100** au moment de
   l'attaque, puis redescend. Visuellement parlant.
9. Ouvre l'alerte → montre l'**explicabilité** (features déviantes) et la
   proposition **SOAR** (gel de compte + préservation logs en auto, isolation en
   attente de validation humaine).

### Acte 4 — La souveraineté (1 min)
10. « Tout ceci s'est passé dans le datacenter : la collecte, le scoring, la
    décision, la visualisation. Aucune donnée de solde n'est sortie. Le CENADI
    possède et audite tout le code (open source, GPL-3.0). »

### Acte 5 — Honnêteté (1 min)
11. Enchaîne sur le §2 : ce qui est réel, ce qui reste à faire (vraies données
    SIGIPES, connecteurs SOAR réels, sonde réseau pour le Modèle 1).

---

## 6. La visualisation des métriques (onglet Supervision)

- **Risque réseau (M1)** et **Risque fraude UEBA (M2)** : 0–100, avec le **seuil
  d'alerte à 70** tracé en pointillé. Une courbe qui franchit 70 = alerte.
- **Événements ingérés** / **Alertes émises** : volumétrie réelle.
- Chaque tuile en haut donne le **dernier point**, la **moyenne** et le **max**.
- Sélecteur de plage : 1 h / 6 h / 24 h / 7 j.

> Pour que les courbes soient vivantes pendant la démo, laisse le **collecteur
> tourner** (service `nexus-collector` ou `--loop`) au moins quelques minutes
> avant de commencer.

---

## 7. Le lab CENADI avec tes VMs

Objectif : reproduire l'architecture souveraine réelle (zones, air-gap, PKI) et
faire tes tests avec de vrais agents.

Topologie (voir `lab-cenadi/00-architecture-cenadi.md`) :
- **HÔTE** = cœur SOC (10.50.0.1) : la pile NEXUS.
- **vm-app-gov** (10.50.20.20) → périmètre **SIGIPES**.
- **vm-antilope** (10.50.30.30, air-gap) → périmètre **ANTILOPE**.
- **vm-rssi** (10.50.40.40) : poste analyste (Firefox → console/portail).
- **vm-menace** (10.50.50.50) : attaquant.

Mise en route (sur chaque VM surveillée) :
```bash
# récupère le vrai collecteur depuis le SOC, enrôle, installe le service
sudo bash lab-cenadi/scripts/vm-app-gov-setup.sh      # → périmètre SIGIPES
sudo bash lab-cenadi/scripts/vm-antilope-setup.sh     # → périmètre ANTILOPE
```

Ce que le lab prouve (démontrable, cf. `lab-cenadi/RUNBOOK.md`) :
1. **Souveraineté** — zéro sortie du datacenter (tcpdump + pare-feu).
2. **Air-gap** — la zone sensible ne joint que le SOC.
3. **Détection d'exfiltration** — scénario 03, alerte réelle.
4. **PKI interne** — HTTPS via l'autorité racine CENADI.

> Pour le Modèle 1 (réseau) : c'est là qu'on peut ajouter une **sonde de flux**
> (NetFlow/CICFlowMeter sur le pare-feu ou un port miroir) pour l'alimenter avec
> de vraies features et retrouver sa performance d'entraînement.

---

## 8. SIEM Wazuh (optionnel, en cours)

Wazuh ajoute la détection par règles sur logs (SSH, sudo, intégrité fichiers) et
ses propres dashboards. Il **n'est pas requis** pour la chaîne IA.

- Statut : script clé-en-main prêt (`Lot0_Socle/setup_wazuh.sh`), images ~3 Go
  en téléchargement.
- Quand les images sont là :
  ```bash
  bash Lot0_Socle/setup_wazuh.sh --check   # vérifier les prérequis
  bash Lot0_Socle/setup_wazuh.sh           # générer certs + démarrer
  ```
- Une fois lancé : dashboard sur `https://<SOC>:5601`, et `/health/detailed`
  passe `wazuh_indexer` → ok.

---

## 9. Messages-clés à retenir

- **Souveraineté** : 100 % open source (GPL-3.0), exploité en interne, aucune
  donnée dehors.
- **Cloisonnement** : périmètres internes (SIGIPES/ANTILOPE/réseau), isolés par RLS.
- **Réel** : télémétrie, pipeline, alertes, supervision — mesurés et fonctionnels.
- **Honnête** : les modèles restent sur données synthétiques ; le terrain viendra
  des vrais journaux SIGIPES/ANTILOPE. C'est une force, pas une faiblesse, de le dire.

---

## Annexe — Commandes de vérification rapide

```bash
# 1. Générer une alerte de démonstration (attaque simulée, pipeline réel)
python3 Lot1_Agent_Go/nexus_collector.py --simulate exfil

# 2. Voir les alertes récentes (API)
TOK=$(curl -s -X POST http://127.0.0.1:8000/auth/token -H 'Content-Type: application/json' \
      -d '{"email":"admin@nexussoc.cm","password":"admin"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s "http://127.0.0.1:8000/analyst/alerts?limit=5" -H "Authorization: Bearer $TOK" | python3 -m json.tool

# 3. Voir les métriques de supervision (API)
curl -s "http://127.0.0.1:8000/admin/metrics?hours=1" -H "Authorization: Bearer $TOK" | python3 -m json.tool

# 4. Isolation RLS (preuve)
python3 Lot7_Console_Fournisseur/rls_analyst_test.py     # 8/8 attendu
```

# NEXUS SOC — Lot 6 : Durcissement et tests

Le lot qui **transforme les promesses du cahier des charges en chiffres mesurés**. Quatre
composants : simulation d'attaques style Atomic Red Team, mesure du MTTD, test de charge du
pipeline, et test d'isolation multi-tenant Row-Level Security exécuté sur un vrai PostgreSQL.

---

## 1. Contenu

| Fichier | Rôle |
|---|---|
| `attack_simulation.py` | Catalogue de techniques MITRE injectées dans le moteur de corrélation + scénarios multi-étapes avec MTTD |
| `load_test.py` | Mesure du débit et de la latence du normaliseur, de l'agrégation et du corrélateur |
| `rls_isolation_test.py` | 5 assertions exécutées contre une vraie base PostgreSQL pour vérifier l'isolation RLS |
| `make_lot6_figures.py` | Génère les figures de synthèse |
| `out_lot6/*.json` | Résultats bruts |
| `out_lot6/*.png` | Figures pour le rapport |

## 2. Simulation d'attaques (style Atomic Red Team)

Pour chaque technique MITRE, on **fabrique les événements de télémétrie** qu'un test réel
produirait (process spawn, fichier déposé, connexion vers un C2…), et on les passe au moteur
de corrélation. C'est exactement ce qu'une équipe rouge fait quand elle ne peut pas tirer en
production. Plus trois **scénarios multi-étapes** pour mesurer le MTTD et un scénario **négatif**
(trafic légitime) pour vérifier l'absence de faux positif.

**Résultats mesurés :**

- **Couverture des techniques attendues : 7/7 (100 %)** — PowerShell, cmd.exe, exécution depuis
  `/tmp`, fichier malveillant en Downloads, accès `/etc/shadow`, C2 sur port 4444, modification
  massive de fichiers.
- **Vrais négatifs : 2/3** — T1083 et T1136 correctement ignorés ; T1027 (obfuscation) attrapée
  *par effet de bord* par la règle « répertoire temporaire » (mauvaise étiquette technique,
  mais détection légitime de l'exécution depuis `C:/temp/`).
- **Scénarios : 3/3** — ransomware détecté à **MTTD = 120 s** (après la 3ᵉ étape, la collecte),
  exfiltration détectée à **MTTD = 90 s**, scénario négatif correctement ignoré (aucune alerte).
- **Lacunes de couverture documentées** pour la feuille de route : T1083 (peu de signal côté
  endpoint), T1136 (relève du Modèle 2 UEBA sur logs SIGIPES), T1027 (à étendre avec règles
  YARA/contenu).

> Le MTTD mesuré ici est *attack-time* : c'est le temps écoulé entre le début de l'attaque et
> le moment où le moteur lève l'incident. La **latence de traitement** du moteur, elle, est
> sub-milliseconde (voir test de charge).

## 3. Test de charge du pipeline

Mesure mono-cœur du débit et de la latence à 1 k, 5 k, 25 k et 100 k événements.

| Composant | Débit (1k → 100k) | Latence p99 |
|---|---|---|
| Normalisation | **229 k → 189 k ev/s** (très stable) | ≤ 12 μs |
| Agrégation features hôte | 278 k → 248 k ev/s | — |
| Corrélation (rules + chaîne) | 714 k → **22 k ev/s** | — |

**Constat honnête** : le moteur de corrélation est très rapide sur les petits lots (< 1 ms pour
1 k événements) mais **dégrade fortement à grand volume**. Le profilage pointe la fonction
`detect_mass_file_change` en O(N²) sur les fichiers d'un même hôte. C'est exactement le genre
de point chaud qu'un test de charge doit faire émerger. **Correctif identifié** : compteur
glissant en O(N) — c'est un point de perspective concret pour le rapport.

> Le pipeline reste **parallélisable** par hôte et par tenant via des consumers Kafka
> indépendants ; ces chiffres sont mono-cœur, pas la limite de la plateforme.

## 4. Isolation multi-tenant (Row-Level Security)

**Test exécuté sur une vraie instance PostgreSQL 16**, schéma du Lot 0 appliqué, deux tenants
peuplés. Cinq assertions, jouées avec un **rôle applicatif `nexus_app` non-privilégié** (point
crucial : le super-utilisateur PostgreSQL contourne TOUJOURS la RLS, même `FORCE ROW LEVEL
SECURITY` — un test joué en `postgres` validerait à tort. L'application ne doit jamais utiliser
le rôle super-utilisateur).

**Résultat : 5/5 assertions vérifiées.**

| # | Assertion | Résultat |
|---|---|---|
| 1 | Tenant A : `COUNT(alerts) = 3` | ✓ |
| 2 | Tenant B : `COUNT(alerts) = 2` | ✓ |
| 3 | Tentative de fuite — A interroge `tenant_id = B` | 0 lignes ✓ |
| 4 | Session sans tenant positionné — `COUNT = 0` | ✓ |
| 5 | Tenant A ne voit QUE des lignes de `tenant_id = A` | ✓ |

**Correctif découvert par le test, propagé au schéma du Lot 0** : la politique RLS doit utiliser
`NULLIF(current_setting('app.current_tenant', true), '')::uuid` pour gérer proprement le cas
d'une variable de session vide (sinon le cast `''::uuid` échoue). Le schéma du socle a été mis
à jour en conséquence — exactement ce à quoi sert un test rigoureux.

## 5. Exécution

```bash
# 1. Simulation d'attaques + MTTD (dépend du moteur de corrélation du Lot 2)
python attack_simulation.py

# 2. Test de charge (volumes croissants)
python load_test.py

# 3. Test d'isolation RLS (requiert PostgreSQL accessible localement, rôle nexus_app créé par le script)
python rls_isolation_test.py

# 4. Génération des figures
python make_lot6_figures.py
```

## 6. Synthèse pour la soutenance

| Promesse du cahier des charges | Preuve mesurée (Lot 6) |
|---|---|
| Détection MITRE | **7/7** techniques attendues couvertes (Lot 2 + simulation) |
| Reconstitution de chaînes d'attaque | **3/3** scénarios — MTTD attack-time 90-120 s |
| Pas de faux positif sur trafic légitime | Scénario négatif → **0 alerte** |
| Performance du pipeline | Normalisation **200 k ev/s** stable, latence p99 ≤ 12 μs (mono-cœur) |
| Isolation multi-tenant | **5/5** assertions RLS sur PostgreSQL réel |

## 7. Pistes (chapitre perspectives)

- **Atomic Red Team / Caldera réels** sur un poste instrumenté pour comparer les MTTD mesurés
  ici (en simulation) avec une exécution authentique.
- **Optimisation O(N) du détecteur de modification massive** (compteur glissant).
- Étendre la couverture MITRE : règles YARA pour T1027, signatures de Discovery (T1083),
  intégration des règles Sigma de la communauté Wazuh.
- Tests de charge **multi-cœurs** et **multi-consumer Kafka** pour démontrer la scalabilité
  horizontale réelle de la plateforme.
- Tests de **résilience** (panne d'un service du socle, perte de connexion réseau, dégradation
  gracieuse de l'agent en store-and-forward).

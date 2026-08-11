# Composants tiers et licences — NEXUS SOC

NEXUS SOC est distribué sous **GPL-3.0-or-later** (voir [`LICENSE`](LICENSE)),
licence copyleft choisie pour sa compatibilité avec Wazuh (GPL v2) et pour
garantir que la plateforme reste librement auditable, modifiable et
redistribuable par le CENADI et tout tiers.

Le tableau ci-dessous liste les composants tiers intégrés ou utilisés par la
plateforme, avec leur licence respective. Chaque composant conserve sa propre
licence ; cette page ne fait que les recenser.

| Composant | Rôle dans NEXUS SOC | Licence |
|---|---|---|
| **Agent Go** (pur stdlib) | Collecte de télémétrie endpoint (Lot 1) | BSD 3-Clause (bibliothèque standard Go) |
| **Apache Kafka** | Bus d'événements du pipeline temps réel | Apache License 2.0 |
| **FastAPI** | Framework de l'API REST (scoring, admin, provisioning) | MIT |
| **scikit-learn** | Modèles IA (Isolation Forest, UEBA) | BSD 3-Clause |
| **NumPy** | Calcul numérique (features, scoring) | BSD 3-Clause |
| **joblib** | Sérialisation des modèles `.joblib` | BSD 3-Clause |
| **psycopg2** | Pilote PostgreSQL synchrone | LGPL 3.0 (avec exception) |
| **Uvicorn** | Serveur ASGI | BSD 3-Clause |
| **Pydantic** | Validation des schémas de l'API | MIT |
| **Wazuh** (Manager, Indexer, Dashboard) | SIEM — stockage chaud, règles, tableau de bord | GPL v2 |
| **PostgreSQL** | Base de données relationnelle | PostgreSQL License (type BSD/MIT) |
| **TimescaleDB** | Extension séries temporelles de PostgreSQL | Apache License 2.0 |
| **Moteur SOAR** (interne) | Playbooks, garde-fous, rollback (Lot 4) | Code interne — GPL-3.0-or-later |
| **Docker / Docker Compose** | Orchestration de la pile | Apache License 2.0 |
| **OpenTofu** | Déploiement souverain (infrastructure-as-code) | MPL 2.0 |

## Notes de compatibilité

- **Wazuh (GPL v2)** est le composant le plus contraignant. Le choix d'une
  licence copyleft **GPL-3.0-or-later** pour NEXUS SOC est compatible avec la
  distribution conjointe : la mention « or-later » permet l'agrégation avec des
  composants GPL v2 « or later » et évite les incompatibilités de version.
- **TimescaleDB** : seule l'édition Community/Apache 2.0 est utilisée ; les
  fonctionnalités sous licence TSL (Timescale License) ne sont pas requises.
- **VirusTotal** (enrichissement IOC) est un **service externe optionnel**,
  appelé via son API publique ; il n'est pas redistribué avec la plateforme et
  reste désactivable (`VIRUSTOTAL_ENABLED=false`).

## Obtention des textes de licence

Les textes complets des licences citées sont disponibles auprès de chaque projet
amont. Sur un système Debian/Ubuntu, plusieurs sont présents dans
`/usr/share/common-licenses/` (Apache-2.0, BSD, GPL-2, GPL-3, LGPL-3, MPL-2.0).

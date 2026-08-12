#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — Mise en route du SIEM Wazuh 4.9 (mono-nœud) — clé en main
# -----------------------------------------------------------------------------
# À lancer une fois que les 3 images Wazuh sont téléchargées (voir --check).
# Le script : (1) génère les certificats si absents, (2) récupère la config
# officielle Wazuh 4.9, (3) démarre indexer + manager + dashboard, (4) initialise
# la sécurité, (5) vérifie. Rejoue-able sans danger.
#
#   bash setup_wazuh.sh --check     # état des images / prérequis
#   bash setup_wazuh.sh             # installe et démarre Wazuh
#   bash setup_wazuh.sh --down      # arrête la pile Wazuh
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

CERTS_DIR="config/wazuh_indexer_ssl_certs"
IDX_CFG="config/wazuh_indexer"
DASH_CFG="config/wazuh_dashboard"
COMPOSE="docker-compose.wazuh.yml"
RAW="https://raw.githubusercontent.com/wazuh/wazuh-docker/v4.9.0/single-node/config"

have_compose() { docker compose version >/dev/null 2>&1; }
DC() { if have_compose; then docker compose "$@"; else docker-compose "$@"; fi; }

check() {
  echo "== Prérequis Wazuh =="
  for img in wazuh-indexer wazuh-manager wazuh-dashboard; do
    if docker image inspect "wazuh/$img:4.9.0" >/dev/null 2>&1; then
      echo "  ✓ image wazuh/$img:4.9.0"
    else
      echo "  ✗ image wazuh/$img:4.9.0 MANQUANTE (docker pull wazuh/$img:4.9.0)"
    fi
  done
  echo "  vm.max_map_count = $(sysctl -n vm.max_map_count 2>/dev/null) (requis >= 262144)"
  have_compose && echo "  ✓ docker compose disponible" || echo "  ✗ docker compose absent"
  echo "  certificats : $(ls "$CERTS_DIR"/*.pem 2>/dev/null | wc -l) fichiers"
}

[[ "${1:-}" == "--check" ]] && { check; exit 0; }
[[ "${1:-}" == "--down"  ]] && { DC -f "$COMPOSE" down; exit 0; }

# --- 1. Certificats ---------------------------------------------------------
if [ ! -f "$CERTS_DIR/wazuh.indexer.pem" ]; then
  echo "== Génération des certificats =="
  mkdir -p "$CERTS_DIR"
  cat > config/certs.yml <<'EOF'
nodes:
  indexer:
    - name: wazuh.indexer
      ip: wazuh.indexer
  server:
    - name: wazuh.manager
      ip: wazuh.manager
  dashboard:
    - name: wazuh.dashboard
      ip: wazuh.dashboard
EOF
  docker run --rm -v "$PWD/config/certs.yml:/config/certs.yml:ro" \
    -v "$PWD/$CERTS_DIR/:/certificates/" wazuh/wazuh-certs-generator:0.0.2
fi

# --- 2. Config officielle Wazuh 4.9 ----------------------------------------
echo "== Récupération de la config officielle Wazuh 4.9 =="
mkdir -p "$IDX_CFG" "$DASH_CFG"
curl -fsSL "$RAW/wazuh_indexer/wazuh.indexer.yml"           -o "$IDX_CFG/opensearch.yml"
curl -fsSL "$RAW/wazuh_indexer/internal_users.yml"          -o "$IDX_CFG/internal_users.yml"
curl -fsSL "$RAW/wazuh_dashboard/opensearch_dashboards.yml" -o "$DASH_CFG/opensearch_dashboards.yml"
curl -fsSL "$RAW/wazuh_dashboard/wazuh.yml"                 -o "$DASH_CFG/wazuh.yml"
# Le nom de nœud dans la config officielle est "wazuh1.indexer" → on l'aligne
sed -i 's/wazuh1\.indexer/wazuh.indexer/g' "$IDX_CFG/opensearch.yml" 2>/dev/null || true

# --- 3. Compose dédié Wazuh -------------------------------------------------
cat > "$COMPOSE" <<'YAML'
name: nexus-wazuh
services:
  wazuh.indexer:
    image: wazuh/wazuh-indexer:4.9.0
    container_name: nexus-wazuh-indexer
    hostname: wazuh.indexer
    restart: unless-stopped
    ports: ["9200:9200"]
    environment: [ "OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g" ]
    ulimits:
      memlock: { soft: -1, hard: -1 }
      nofile:  { soft: 65536, hard: 65536 }
    volumes:
      - indexer_data:/var/lib/wazuh-indexer
      - ./config/wazuh_indexer/opensearch.yml:/usr/share/wazuh-indexer/opensearch.yml
      - ./config/wazuh_indexer/internal_users.yml:/usr/share/wazuh-indexer/opensearch-security/internal_users.yml
      - ./config/wazuh_indexer_ssl_certs/root-ca.pem:/usr/share/wazuh-indexer/certs/root-ca.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.indexer.pem:/usr/share/wazuh-indexer/certs/wazuh.indexer.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.indexer-key.pem:/usr/share/wazuh-indexer/certs/wazuh.indexer.key
      - ./config/wazuh_indexer_ssl_certs/admin.pem:/usr/share/wazuh-indexer/certs/admin.pem
      - ./config/wazuh_indexer_ssl_certs/admin-key.pem:/usr/share/wazuh-indexer/certs/admin.key
    networks: [nexus]

  wazuh.manager:
    image: wazuh/wazuh-manager:4.9.0
    container_name: nexus-wazuh-manager
    hostname: wazuh.manager
    restart: unless-stopped
    depends_on: [wazuh.indexer]
    ports: ["1514:1514","1515:1515","55000:55000"]
    ulimits: { memlock: { soft: -1, hard: -1 } }
    # Ces variables font remplir la sortie filebeat -> indexer (TLS + creds).
    # Sans elles, filebeat.yml reste en template commenté et AUCUN index
    # wazuh-alerts-* n'est créé (« No matching indices » dans le dashboard).
    environment:
      - INDEXER_URL=https://wazuh.indexer:9200
      - INDEXER_USERNAME=admin
      - INDEXER_PASSWORD=admin
      - FILEBEAT_SSL_VERIFICATION_MODE=full
    volumes:
      - manager_data:/var/ossec
      - ./config/wazuh_indexer_ssl_certs/root-ca.pem:/etc/ssl/root-ca.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.manager.pem:/etc/ssl/filebeat.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.manager-key.pem:/etc/ssl/filebeat.key
    networks: [nexus]

  wazuh.dashboard:
    image: wazuh/wazuh-dashboard:4.9.0
    container_name: nexus-wazuh-dashboard
    hostname: wazuh.dashboard
    restart: unless-stopped
    depends_on: [wazuh.indexer]
    ports: ["5601:5601"]
    environment:
      - INDEXER_URL=https://wazuh.indexer:9200
      - INDEXER_USERNAME=admin
      - INDEXER_PASSWORD=admin
      - DASHBOARD_USERNAME=kibanaserver
      - DASHBOARD_PASSWORD=kibanaserver
    volumes:
      - ./config/wazuh_dashboard/opensearch_dashboards.yml:/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml
      - ./config/wazuh_dashboard/wazuh.yml:/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml
      - ./config/wazuh_indexer_ssl_certs/root-ca.pem:/usr/share/wazuh-dashboard/certs/root-ca.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.dashboard.pem:/usr/share/wazuh-dashboard/certs/wazuh-dashboard.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.dashboard-key.pem:/usr/share/wazuh-dashboard/certs/wazuh-dashboard-key.pem
    networks: [nexus]

volumes:
  indexer_data:
  manager_data:
networks:
  nexus:
    name: nexus
    external: true
YAML

# Le réseau "nexus" doit exister (créé par la pile principale). Sinon on le crée.
docker network inspect nexus >/dev/null 2>&1 || docker network create nexus

# --- 4. Démarrage ----------------------------------------------------------
echo "== Démarrage de l'indexer =="
DC -f "$COMPOSE" up -d wazuh.indexer
echo "   attente du démarrage de l'indexer (~60-90s)..."
for i in $(seq 1 40); do
  docker exec nexus-wazuh-indexer curl -sk -u admin:admin https://localhost:9200/_cluster/health >/dev/null 2>&1 && break
  sleep 5
done

# Fixer le mot de passe admin de l'indexer à « admin » (ce qu'attend le
# healthcheck NEXUS). On génère le hash bcrypt via l'outil de l'indexer, puis on
# l'injecte dans internal_users.yml (monté) AVANT le chargement de la config.
echo "== Mot de passe admin de l'indexer -> 'admin' =="
HASH=$(docker exec nexus-wazuh-indexer bash -lc \
  'JAVA_HOME=/usr/share/wazuh-indexer/jdk bash /usr/share/wazuh-indexer/plugins/opensearch-security/tools/hash.sh -p admin 2>/dev/null | tail -1')
if [ -n "$HASH" ]; then
  python3 - "$HASH" "$IDX_CFG/internal_users.yml" <<'PY'
import sys, re
h, p = sys.argv[1], sys.argv[2]
s = open(p).read()
s = re.sub(r'(admin:\s*\n\s*hash:\s*")[^"]+(")', lambda m: m.group(1)+h+m.group(2), s, count=1)
open(p, "w").write(s)
print("   internal_users.yml : hash admin mis à jour")
PY
fi

echo "== Initialisation de la sécurité (securityadmin) =="
# JAVA_HOME requis : le conteneur n'a pas 'which' utilisé par securityadmin.sh
docker exec nexus-wazuh-indexer bash -lc '
  export JAVA_HOME=/usr/share/wazuh-indexer/jdk
  export PATH=$JAVA_HOME/bin:$PATH
  D=/usr/share/wazuh-indexer
  bash $D/plugins/opensearch-security/tools/securityadmin.sh \
    -cd $D/opensearch-security/ -nhnv \
    -cacert $D/certs/root-ca.pem -cert $D/certs/admin.pem \
    -key $D/certs/admin.key -p 9200 -icl' || \
  echo "   (securityadmin : à relancer si l'indexer n'était pas prêt)"

echo "== Démarrage manager + dashboard =="
DC -f "$COMPOSE" up -d wazuh.manager wazuh.dashboard

# Filet de sécurité : si la sortie filebeat est restée en template commenté
# (SSL désactivé), on la remplit et on relance filebeat. Sans ça, aucun index
# wazuh-alerts-* n'est créé → « No matching indices » dans le dashboard.
echo "== Filebeat -> indexer : vérification de la sortie TLS =="
sleep 15
if docker exec nexus-wazuh-manager grep -q '^  #ssl.certificate_authorities:' /etc/filebeat/filebeat.yml 2>/dev/null; then
  echo "   sortie filebeat non configurée → correction"
  docker exec nexus-wazuh-manager sh -c "sed -i \
    -e \"s|^  #username:.*|  username: 'admin'|\" \
    -e \"s|^  #password:.*|  password: 'admin'|\" \
    -e \"s|^  #ssl.certificate_authorities:.*|  ssl.certificate_authorities: ['/etc/ssl/root-ca.pem']|\" \
    -e \"s|^  #ssl.certificate:.*|  ssl.certificate: '/etc/ssl/filebeat.pem'|\" \
    -e \"s|^  #ssl.key:.*|  ssl.key: '/etc/ssl/filebeat.key'|\" \
    /etc/filebeat/filebeat.yml"
  docker restart nexus-wazuh-manager >/dev/null 2>&1
  echo "   ✓ filebeat corrigé et relancé"
else
  echo "   ✓ sortie filebeat déjà configurée"
fi

echo
echo "== Vérification =="
sleep 5
echo -n "  indexer  : "; curl -sk -u admin:admin https://localhost:9200/_cluster/health 2>/dev/null | head -c 120; echo
echo -n "  alertes  : "; curl -sk -u admin:admin "https://localhost:9200/_cat/indices/wazuh-alerts-*?h=index,docs.count" 2>/dev/null | head -1 || echo "index pas encore créé (attendre ~1 min)"
echo "  dashboard: https://localhost:5601  (admin / admin) — démarre en ~2 min"
echo "  NEXUS /health/detailed devrait passer wazuh_indexer -> ok"

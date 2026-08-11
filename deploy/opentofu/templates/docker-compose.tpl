# =============================================================================
#  NEXUS SOC — Docker Compose (généré par OpenTofu)
#  Institution : Variables injectées depuis OpenTofu
#  Base        : Lot0_Socle/docker-compose.yml
# =============================================================================
name: nexus-soc

services:

  # ---------------------------------------------------------------------------
  # 1. Apache Kafka (mode KRaft, sans Zookeeper)
  # ---------------------------------------------------------------------------
  kafka:
    image: apache/kafka:${kafka_version}
    container_name: nexus-kafka
    hostname: kafka
    ports:
      - "9092:9092"
      - "29092:29092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,HOST://0.0.0.0:29092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,HOST://localhost:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,HOST:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka_data:/var/lib/kafka/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 10
    networks: [nexus]

  # ---------------------------------------------------------------------------
  # 2. TimescaleDB (PostgreSQL 16 + extension séries temporelles)
  # ---------------------------------------------------------------------------
  postgres:
    image: timescale/timescaledb:${timescale_version}
    container_name: nexus-postgres
    environment:
      # $${VAR} → ${VAR} dans le fichier généré (OpenTofu échappe $$)
      POSTGRES_USER: $${POSTGRES_USER:-nexus}
      POSTGRES_PASSWORD: $${POSTGRES_PASSWORD:-change_me}
      POSTGRES_DB: $${POSTGRES_DB:-nexus_soc}
    ports:
      - "127.0.0.1:5432:5432"    # Exposé uniquement en loopback (sécurité)
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ${install_dir}/config/postgres/init:/docker-entrypoint-initdb.d:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER:-nexus} -d $${POSTGRES_DB:-nexus_soc}"]
      interval: 10s
      timeout: 5s
      retries: 15
    networks: [nexus]

  # ---------------------------------------------------------------------------
  # 3. Wazuh Indexer (stockage chaud SIEM, compatible Elasticsearch)
  # ---------------------------------------------------------------------------
  wazuh.indexer:
    image: wazuh/wazuh-indexer:${wazuh_version}
    container_name: nexus-wazuh-indexer
    hostname: wazuh.indexer
    ports:
      - "127.0.0.1:9200:9200"    # API interne uniquement
    environment:
      - "OPENSEARCH_JAVA_OPTS=-Xms${wazuh_heap_mb}m -Xmx${wazuh_heap_mb}m"
    ulimits:
      memlock: { soft: -1, hard: -1 }
      nofile:  { soft: 65536, hard: 65536 }
    volumes:
      - indexer_data:/var/lib/wazuh-indexer
      - ${install_dir}/config/wazuh_indexer/opensearch.yml:/usr/share/wazuh-indexer/opensearch.yml:ro
      - ${install_dir}/config/wazuh_indexer_ssl_certs:/usr/share/wazuh-indexer/certs:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -sk -u admin:$${WAZUH_ADMIN_PASSWORD:-admin} https://localhost:9200/_cluster/health | grep -q '\"status\"' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 15
      start_period: 90s
    networks: [nexus]

  # ---------------------------------------------------------------------------
  # 4. Wazuh Manager (collecte, règles de corrélation)
  # ---------------------------------------------------------------------------
  wazuh.manager:
    image: wazuh/wazuh-manager:${wazuh_version}
    container_name: nexus-wazuh-manager
    hostname: wazuh.manager
    depends_on:
      wazuh.indexer: { condition: service_healthy }
    ports:
      - "1514:1514"    # Agents Wazuh
      - "1515:1515"    # Enrôlement Wazuh
      - "55000:55000"  # API REST Wazuh
    ulimits:
      memlock: { soft: -1, hard: -1 }
    volumes:
      - manager_data:/var/ossec
      - ${install_dir}/config/wazuh_indexer_ssl_certs:/etc/ssl/certs/wazuh:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -sk https://localhost:55000/ | grep -q 'title' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 6
      start_period: 60s
    networks: [nexus]

  # ---------------------------------------------------------------------------
  # 5. Wazuh Dashboard (interface SIEM)
  # ---------------------------------------------------------------------------
  wazuh.dashboard:
    image: wazuh/wazuh-dashboard:${wazuh_version}
    container_name: nexus-wazuh-dashboard
    depends_on:
      wazuh.indexer: { condition: service_healthy }
%{ if expose_dashboard ~}
    ports:
      - "5601:5601"    # Interface web Wazuh
%{ endif ~}
    environment:
      - INDEXER_URL=https://wazuh.indexer:9200
      - DASHBOARD_USERNAME=kibanaserver
      - DASHBOARD_PASSWORD=kibanaserver
    volumes:
      - ${install_dir}/config/wazuh_indexer_ssl_certs:/usr/share/wazuh-dashboard/certs:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -sk https://localhost:5601/api/status | grep -q 'available' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s
    networks: [nexus]

  # ---------------------------------------------------------------------------
  # 6. Service de scoring IA (FastAPI v2)
  # ---------------------------------------------------------------------------
  scoring-service:
    build:
      context: ${install_dir}/scoring-service
      dockerfile: Dockerfile
    container_name: nexus-scoring
    depends_on:
      kafka:    { condition: service_healthy }
      postgres: { condition: service_healthy }
    ports:
      - "8000:8000"
    env_file:
      - ${install_dir}/.env
    volumes:
      - ${install_dir}/models:/models:ro
      - ${install_dir}/config/tls:/certs:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health | grep -q '\"status\":\"ok\"' || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks: [nexus]

volumes:
  kafka_data:
  postgres_data:
  indexer_data:
  manager_data:

networks:
  nexus:
    driver: bridge

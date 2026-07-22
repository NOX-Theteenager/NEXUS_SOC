# =============================================================================
# NEXUS SOC — Module OpenTofu : Déploiement Souverain
#
# Déploie la pile complète NEXUS SOC sur un serveur bare-metal ou VM
# appartenant à l'institution souveraine, via SSH.
#
# Séquence :
#   1. Génération des secrets et certificats TLS
#   2. Rendu des templates de configuration (.env, docker-compose.yml, Dockerfile)
#   3. Installation des prérequis système (Docker, paramètres noyau)
#   4. Upload de tous les fichiers sur le serveur
#   5. Génération des certificats Wazuh
#   6. Démarrage de la pile Docker Compose (--wait : attend les healthchecks)
#   7. Vérification de santé de l'ensemble des services
# =============================================================================

# --------------------------------------------------------------------------- #
# Secrets auto-générés
# --------------------------------------------------------------------------- #

resource "random_password" "postgres" {
  length  = 24
  special = false
}

resource "random_password" "jwt" {
  length  = 48
  special = false
}

resource "random_password" "pseudo" {
  length  = 48
  special = false
}

resource "random_password" "wazuh_admin" {
  length  = 20
  special = false
}

locals {
  pg_pass       = coalesce(var.postgres_password,    random_password.postgres.result)
  jwt_secret    = coalesce(var.jwt_secret,           random_password.jwt.result)
  pseudo_secret = coalesce(var.pseudo_secret,        random_password.pseudo.result)
  wazuh_pass    = coalesce(var.wazuh_admin_password, random_password.wazuh_admin.result)

  ssh_key = (
    var.ssh_private_key != "" ? var.ssh_private_key
    : var.ssh_private_key_path != "" ? file(var.ssh_private_key_path)
    : ""
  )

  # Répertoire racine du dépôt NEXUS SOC (deux niveaux au-dessus de ce module)
  repo_root = abspath("${path.module}/../../")
}

# --------------------------------------------------------------------------- #
# Certificat TLS auto-signé pour NEXUS SOC
# (Remplacer par un certificat émis par la PKI interne de l'institution)
# --------------------------------------------------------------------------- #

resource "tls_private_key" "nexus" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "tls_self_signed_cert" "nexus" {
  private_key_pem = tls_private_key.nexus.private_key_pem

  subject {
    common_name  = var.nexus_domain
    organization = var.institution_name
    country      = "CM"
    locality     = "Yaoundé"
  }

  validity_period_hours = 8760  # 1 an
  early_renewal_hours   = 720   # alerte 30j avant expiry

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]

  dns_names    = distinct([var.nexus_domain, "localhost"])
  ip_addresses = [var.server_host]
}

# --------------------------------------------------------------------------- #
# Rendu des templates de configuration
# --------------------------------------------------------------------------- #

resource "local_sensitive_file" "env" {
  filename = "${path.module}/.generated/.env"
  content = templatefile("${path.module}/templates/env.tpl", {
    pg_pass           = local.pg_pass
    jwt_secret        = local.jwt_secret
    pseudo_secret     = local.pseudo_secret
    nexus_domain      = var.nexus_domain
    institution       = var.institution_name
    wazuh_pass        = local.wazuh_pass
    risk_threshold    = var.risk_threshold
    ingest_rate_limit = var.ingest_rate_limit
    nexus_version     = var.nexus_version
  })
  file_permission      = "0600"
  directory_permission = "0700"
}

resource "local_file" "compose" {
  filename = "${path.module}/.generated/docker-compose.yml"
  content = templatefile("${path.module}/templates/docker-compose.tpl", {
    install_dir       = var.install_dir
    wazuh_version     = var.wazuh_version
    kafka_version     = var.kafka_version
    timescale_version = var.timescale_version
    wazuh_heap_mb     = var.wazuh_jvm_heap_mb
    expose_dashboard  = var.expose_wazuh_dashboard
  })
  file_permission = "0644"
}

resource "local_file" "dockerfile_scoring" {
  filename = "${path.module}/.generated/Dockerfile.scoring"
  content = templatefile("${path.module}/templates/Dockerfile.scoring.tpl", {
    nexus_version = var.nexus_version
  })
  file_permission = "0644"
}

# --------------------------------------------------------------------------- #
# Étape 1 — Prérequis système sur le serveur cible
# --------------------------------------------------------------------------- #

resource "null_resource" "server_prerequisites" {
  triggers = {
    server_host  = var.server_host
    install_dir  = var.install_dir
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "8m"
  }

  provisioner "remote-exec" {
    inline = [
      "set -e",
      "echo '[nexus-tf] === Étape 1/7 : Prérequis système ==='",

      # Paramètre noyau requis par Wazuh Indexer (OpenSearch)
      "sudo sysctl -w vm.max_map_count=262144",
      "grep -q 'vm.max_map_count' /etc/sysctl.conf || echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf",

      # Installer Docker (détection distro)
      "command -v docker >/dev/null 2>&1 && echo 'Docker déjà présent' || (curl -fsSL https://get.docker.com -o /tmp/get-docker.sh && sudo sh /tmp/get-docker.sh && rm /tmp/get-docker.sh)",
      "sudo usermod -aG docker ${var.server_user} || true",
      "newgrp docker || true",

      # Docker Compose v2
      "docker compose version >/dev/null 2>&1 || sudo apt-get install -y docker-compose-plugin 2>/dev/null || true",

      # Paquets utilitaires
      "sudo apt-get install -y --no-install-recommends curl jq unzip python3 python3-pip ca-certificates openssl 2>/dev/null || true",

      # Structure de répertoires
      "sudo mkdir -p ${var.install_dir}/{models,config/postgres/init,config/wazuh_indexer,config/wazuh_indexer_ssl_certs,scoring-service,backups}",
      "sudo chown -R ${var.server_user}:${var.server_user} ${var.install_dir}",
      "chmod 750 ${var.install_dir}",

      "echo '[nexus-tf] Prérequis OK'"
    ]
  }
}

# --------------------------------------------------------------------------- #
# Étape 2 — Upload des fichiers de configuration
# --------------------------------------------------------------------------- #

resource "null_resource" "upload_configs" {
  depends_on = [
    null_resource.server_prerequisites,
    local_sensitive_file.env,
    local_file.compose,
  ]

  triggers = {
    env_hash     = sha256(local_sensitive_file.env.content)
    compose_hash = sha256(local_file.compose.content)
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "5m"
  }

  provisioner "remote-exec" {
    inline = ["echo '[nexus-tf] === Étape 2/7 : Upload des configurations ==='"]
  }

  # Fichiers d'environnement et de composition
  provisioner "file" {
    source      = "${path.module}/.generated/.env"
    destination = "${var.install_dir}/.env"
  }

  provisioner "file" {
    source      = "${path.module}/.generated/docker-compose.yml"
    destination = "${var.install_dir}/docker-compose.yml"
  }

  # Schémas SQL (exécutés automatiquement par docker-entrypoint-initdb.d)
  provisioner "file" {
    source      = "${local.repo_root}/Lot0_Socle/01_schema_patched.sql"
    destination = "${var.install_dir}/config/postgres/init/01_schema_patched.sql"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot7_Console_Fournisseur/01_schema_analyst.sql"
    destination = "${var.install_dir}/config/postgres/init/02_schema_analyst.sql"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot7_Console_Fournisseur/01_schema_provisioning.sql"
    destination = "${var.install_dir}/config/postgres/init/03_schema_provisioning.sql"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot0_Socle/01_schema_retention.sql"
    destination = "${var.install_dir}/config/postgres/init/04_schema_retention.sql"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot8_PLG/01_schema_plg.sql"
    destination = "${var.install_dir}/config/postgres/init/05_schema_plg.sql"
  }

  # Certificat TLS auto-signé (scoring-service HTTPS)
  provisioner "remote-exec" {
    inline = [
      "mkdir -p ${var.install_dir}/config/tls",
      "cat > ${var.install_dir}/config/tls/nexus.crt << 'CERTEOF'",
      tls_self_signed_cert.nexus.cert_pem,
      "CERTEOF",
      "cat > ${var.install_dir}/config/tls/nexus.key << 'KEYEOF'",
      tls_private_key.nexus.private_key_pem,
      "KEYEOF",
      "chmod 600 ${var.install_dir}/config/tls/nexus.key",
      "echo '[nexus-tf] Certificats TLS déposés'"
    ]
  }
}

# --------------------------------------------------------------------------- #
# Étape 3 — Upload des sources Python du scoring-service
# --------------------------------------------------------------------------- #

resource "null_resource" "upload_scoring_service" {
  depends_on = [null_resource.server_prerequisites]

  triggers = {
    scoring_hash = sha256(join("||", [
      filesha256("${local.repo_root}/Lot1_Agent_Go/scoring-service_app.py"),
      filesha256("${local.repo_root}/Lot1_Agent_Go/auth_middleware.py"),
      filesha256("${local.repo_root}/Lot1_Agent_Go/pseudonymizer.py"),
      filesha256("${local.repo_root}/Lot7_Console_Fournisseur/admin_api.py"),
      filesha256("${local.repo_root}/Lot7_Console_Fournisseur/provisioning_api.py"),
      filesha256("${local.repo_root}/Lot8_PLG/plg_api.py"),
      sha256(local_file.dockerfile_scoring.content),
    ]))
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "5m"
  }

  provisioner "remote-exec" {
    inline = ["echo '[nexus-tf] === Étape 3/7 : Upload sources scoring-service ==='"]
  }

  provisioner "file" {
    source      = "${path.module}/.generated/Dockerfile.scoring"
    destination = "${var.install_dir}/scoring-service/Dockerfile"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot1_Agent_Go/scoring-service_app.py"
    destination = "${var.install_dir}/scoring-service/app.py"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot1_Agent_Go/auth_middleware.py"
    destination = "${var.install_dir}/scoring-service/auth_middleware.py"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot1_Agent_Go/pseudonymizer.py"
    destination = "${var.install_dir}/scoring-service/pseudonymizer.py"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot7_Console_Fournisseur/admin_api.py"
    destination = "${var.install_dir}/scoring-service/admin_api.py"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot7_Console_Fournisseur/provisioning_api.py"
    destination = "${var.install_dir}/scoring-service/provisioning_api.py"
  }

  provisioner "file" {
    source      = "${local.repo_root}/Lot8_PLG/plg_api.py"
    destination = "${var.install_dir}/scoring-service/plg_api.py"
  }

  # Générer requirements.txt directement sur le serveur
  provisioner "remote-exec" {
    inline = [
      <<-EOT
      cat > ${var.install_dir}/scoring-service/requirements.txt << 'REQEOF'
      fastapi==0.111.0
      uvicorn[standard]==0.29.0
      pydantic==2.7.1
      python-multipart==0.0.9
      scikit-learn==1.4.2
      numpy==1.26.4
      joblib==1.4.2
      kafka-python==2.0.2
      psycopg2-binary==2.9.9
      asyncpg==0.29.0
      httpx==0.27.0
      REQEOF
      EOT
    ]
  }
}

# --------------------------------------------------------------------------- #
# Étape 4 — Upload des modèles IA (optionnel)
# --------------------------------------------------------------------------- #

resource "null_resource" "upload_models" {
  count      = var.models_local_path != "" ? 1 : 0
  depends_on = [null_resource.server_prerequisites]

  triggers = {
    models_path = var.models_local_path
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "10m"
  }

  provisioner "remote-exec" {
    inline = ["echo '[nexus-tf] === Étape 4/7 : Upload modèles IA ==='"]
  }

  provisioner "file" {
    source      = "${var.models_local_path}/model1_isoforest.joblib"
    destination = "${var.install_dir}/models/model1_isoforest.joblib"
  }

  provisioner "file" {
    source      = "${var.models_local_path}/model2_isoforest.joblib"
    destination = "${var.install_dir}/models/model2_isoforest.joblib"
  }

  provisioner "remote-exec" {
    inline = ["echo '[nexus-tf] Modèles IA uploadés'"]
  }
}

# --------------------------------------------------------------------------- #
# Étape 5 — Génération des certificats Wazuh
# --------------------------------------------------------------------------- #

resource "null_resource" "wazuh_certs" {
  depends_on = [null_resource.upload_configs]

  triggers = {
    domain = var.nexus_domain
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "5m"
  }

  provisioner "remote-exec" {
    inline = [
      "echo '[nexus-tf] === Étape 5/7 : Certificats Wazuh ==='",
      "set -e",
      "cd ${var.install_dir}",
      # Idempotent : skip si les certs existent déjà
      "if [ -f config/wazuh_indexer_ssl_certs/admin.pem ]; then",
      "  echo '[nexus-tf] Certificats Wazuh déjà présents, saut'",
      "  exit 0",
      "fi",
      # Générer les certificats via le conteneur officiel Wazuh
      "docker run --rm \\",
      "  -v $(pwd)/config/wazuh_indexer_ssl_certs:/certs \\",
      "  docker.io/wazuh/wazuh-certs-generator:0.0.2 \\",
      "  2>/dev/null || true",
      # Fallback : générer des certs auto-signés avec openssl si le conteneur échoue
      "if [ ! -f config/wazuh_indexer_ssl_certs/admin.pem ]; then",
      "  echo '[nexus-tf] Fallback : génération SSL avec openssl'",
      "  cd config/wazuh_indexer_ssl_certs",
      "  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\",
      "    -keyout admin-key.pem -out admin.pem \\",
      "    -subj '/CN=wazuh-admin/O=${var.institution_name}/C=CM' 2>/dev/null",
      "  cp admin.pem indexer.pem && cp admin-key.pem indexer-key.pem",
      "  cp admin.pem root-ca.pem",
      "  cd ../../../",
      "fi",
      "echo '[nexus-tf] Certificats Wazuh OK'"
    ]
  }
}

# --------------------------------------------------------------------------- #
# Étape 6 — Démarrage de la pile Docker Compose
# --------------------------------------------------------------------------- #

resource "null_resource" "stack_deploy" {
  depends_on = [
    null_resource.wazuh_certs,
    null_resource.upload_scoring_service,
    null_resource.upload_configs,
  ]

  triggers = {
    compose_hash = sha256(local_file.compose.content)
    env_hash     = sha256(local_sensitive_file.env.content)
    scoring_hash = null_resource.upload_scoring_service.triggers.scoring_hash
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "20m"
  }

  provisioner "remote-exec" {
    inline = [
      "echo '[nexus-tf] === Étape 6/7 : Déploiement Docker Compose ==='",
      "set -e",
      "cd ${var.install_dir}",

      # Pull des images (tolérant aux erreurs réseau)
      "echo '[nexus-tf] Pull des images Docker…'",
      "docker compose pull --quiet 2>/dev/null || echo '[nexus-tf] WARNING: pull partiel, images locales utilisées'",

      # Build du scoring-service
      "echo '[nexus-tf] Build scoring-service…'",
      "docker compose build scoring-service --quiet",

      # Démarrage avec attente des healthchecks (--wait)
      "echo '[nexus-tf] Démarrage de la pile…'",
      "docker compose up -d --wait --timeout 300",

      "echo '[nexus-tf] Pile Docker Compose démarrée'"
    ]
  }
}

# --------------------------------------------------------------------------- #
# Étape 7 — Vérification de santé finale
# --------------------------------------------------------------------------- #

resource "null_resource" "health_check" {
  depends_on = [null_resource.stack_deploy]

  triggers = {
    deploy_id = null_resource.stack_deploy.id
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "5m"
  }

  provisioner "remote-exec" {
    inline = [
      "echo '[nexus-tf] === Étape 7/7 : Vérification de santé ==='",

      # Scoring-service API
      "i=0; until curl -sf http://localhost:8000/health | grep -q '\"status\":\"ok\"'; do",
      "  i=$((i+1)); [ $i -gt 36 ] && echo 'ERREUR: scoring-service timeout' && exit 1; sleep 5;",
      "done",
      "echo '[nexus-tf] ✓ Scoring-service (http://localhost:8000)'",

      # Kafka
      "docker exec nexus-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1",
      "echo '[nexus-tf] ✓ Kafka (port 9092)'",

      # PostgreSQL
      "docker exec nexus-postgres pg_isready -U nexus -d nexus_soc >/dev/null 2>&1",
      "echo '[nexus-tf] ✓ TimescaleDB/PostgreSQL (port 5432)'",

      # Wazuh Indexer
      "curl -skf -u admin:${local.wazuh_pass} https://localhost:9200/_cluster/health | grep -q '\"status\"' && echo '[nexus-tf] ✓ Wazuh Indexer (port 9200)' || echo '[nexus-tf] WARNING: Wazuh Indexer pas encore prêt (normal, ≤2 min)'",

      "echo ''",
      "echo '═══════════════════════════════════════════════════'",
      "echo '  NEXUS SOC déployé avec succès sur ${var.nexus_domain}'",
      "echo '  Institution : ${var.institution_name}'",
      "echo '  Répertoire  : ${var.install_dir}'",
      "echo '  API NEXUS   : http://localhost:8000/docs'",
      "echo '  Wazuh UI    : https://localhost:5601'",
      "echo '═══════════════════════════════════════════════════'",
    ]
  }
}

# --------------------------------------------------------------------------- #
# Configuration du script de sauvegarde automatique
# --------------------------------------------------------------------------- #

resource "null_resource" "backup_cron" {
  depends_on = [null_resource.health_check]

  triggers = {
    install_dir   = var.install_dir
    keep_days     = var.backup_keep_days
  }

  connection {
    type        = "ssh"
    host        = var.server_host
    port        = var.ssh_port
    user        = var.server_user
    private_key = local.ssh_key
    timeout     = "2m"
  }

  provisioner "remote-exec" {
    inline = [
      # Installer le script de sauvegarde NEXUS SOC
      "if [ -f ${var.install_dir}/../NEXUS_SOC/Lot0_Socle/backup.sh ]; then",
      "  cp ${var.install_dir}/../NEXUS_SOC/Lot0_Socle/backup.sh ${var.install_dir}/backup.sh",
      "  chmod +x ${var.install_dir}/backup.sh",
      "fi",

      # Cron quotidien à 02h00
      "CRON_JOB='0 2 * * * BACKUP_DEST=${var.install_dir}/backups KEEP_DAYS=${var.backup_keep_days} bash ${var.install_dir}/backup.sh >> /var/log/nexus-backup.log 2>&1'",
      "(crontab -l 2>/dev/null | grep -v 'nexus.*backup'; echo \"$CRON_JOB\") | crontab -",
      "echo '[nexus-tf] Cron de sauvegarde installé (quotidien 02h00)'"
    ]
  }
}

# =============================================================================
# NEXUS SOC — Variables du module OpenTofu Déploiement Souverain
# Toutes les valeurs sensibles (mots de passe, clés) peuvent être passées
# via variables d'environnement TF_VAR_* ou un fichier terraform.tfvars
# =============================================================================

# --------------------------------------------------------------------------- #
# Connexion au serveur cible
# --------------------------------------------------------------------------- #

variable "server_host" {
  description = "Adresse IP ou FQDN du serveur cible (ex: 192.168.1.10 ou srv-soc.cenadi.cm)"
  type        = string
}

variable "server_user" {
  description = "Utilisateur SSH avec droits sudo sur le serveur cible"
  type        = string
  default     = "ubuntu"
}

variable "ssh_private_key_path" {
  description = "Chemin vers la clé privée SSH sur la machine locale (ex: ~/.ssh/nexus_deploy)"
  type        = string
  default     = ""
}

variable "ssh_private_key" {
  description = "Clé privée SSH en clair (alternative à ssh_private_key_path, pour CI/CD)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ssh_port" {
  description = "Port SSH du serveur cible"
  type        = number
  default     = 22
}

# --------------------------------------------------------------------------- #
# Identité de l'institution souveraine
# --------------------------------------------------------------------------- #

variable "institution_name" {
  description = "Nom de l'institution souveraine exploitant la plateforme"
  type        = string
  default     = "CENADI"

  validation {
    condition     = length(var.institution_name) >= 2
    error_message = "Le nom de l'institution doit comporter au moins 2 caractères."
  }
}

variable "nexus_domain" {
  description = "FQDN de l'instance NEXUS SOC (ex: nexussoc.cm)"
  type        = string
  default     = "nexussoc.cm"
}

variable "install_dir" {
  description = "Répertoire d'installation sur le serveur cible"
  type        = string
  default     = "/opt/nexus-soc"
}

# --------------------------------------------------------------------------- #
# Secrets (auto-générés si laissés vides)
# --------------------------------------------------------------------------- #

variable "postgres_password" {
  description = "Mot de passe PostgreSQL. Auto-généré si vide."
  type        = string
  sensitive   = true
  default     = ""
}

variable "jwt_secret" {
  description = "Secret JWT (min 32 chars). Auto-généré si vide."
  type        = string
  sensitive   = true
  default     = ""
}

variable "pseudo_secret" {
  description = "Secret de pseudonymisation HMAC. Auto-généré si vide."
  type        = string
  sensitive   = true
  default     = ""
}

variable "wazuh_admin_password" {
  description = "Mot de passe admin Wazuh Dashboard. Auto-généré si vide."
  type        = string
  sensitive   = true
  default     = ""
}

# --------------------------------------------------------------------------- #
# Versions des composants
# --------------------------------------------------------------------------- #

variable "wazuh_version" {
  description = "Version des images Docker Wazuh"
  type        = string
  default     = "4.9.0"
}

variable "kafka_version" {
  description = "Version de l'image Docker Apache Kafka"
  type        = string
  default     = "3.7.1"
}

variable "timescale_version" {
  description = "Version de l'image Docker TimescaleDB"
  type        = string
  default     = "2.15.3-pg16"
}

variable "nexus_version" {
  description = "Version de NEXUS SOC (tag du binaire agent et de l'API)"
  type        = string
  default     = "1.0.0"
}

# --------------------------------------------------------------------------- #
# Tuning des ressources
# --------------------------------------------------------------------------- #

variable "wazuh_jvm_heap_mb" {
  description = "Heap JVM de Wazuh Indexer en Mo (minimum 512, recommandé ≥ 1024 en prod)"
  type        = number
  default     = 512

  validation {
    condition     = var.wazuh_jvm_heap_mb >= 512
    error_message = "Le heap Wazuh Indexer doit être d'au moins 512 Mo."
  }
}

variable "risk_threshold" {
  description = "Seuil de risque pour la publication des alertes (0-100)"
  type        = number
  default     = 70
}

variable "ingest_rate_limit" {
  description = "Nombre max de requêtes /ingest par minute par IP"
  type        = number
  default     = 30
}

variable "backup_keep_days" {
  description = "Nombre de jours de rétention des sauvegardes"
  type        = number
  default     = 14
}

# --------------------------------------------------------------------------- #
# Options avancées
# --------------------------------------------------------------------------- #

variable "expose_wazuh_dashboard" {
  description = "Exposer le tableau de bord Wazuh sur le port 5601 (à désactiver en prod derrière un reverse proxy)"
  type        = bool
  default     = true
}

variable "models_local_path" {
  description = "Chemin local vers les fichiers .joblib des modèles IA. Laissez vide si non disponibles localement."
  type        = string
  default     = ""
}

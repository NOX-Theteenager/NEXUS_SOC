terraform {
  required_version = ">= 1.6"

  required_providers {
    # Provisioners SSH (null_resource + remote-exec / file)
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    # Génération de certificats TLS auto-signés
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    # Écriture de fichiers locaux (configs, .env)
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
    # Génération de mots de passe aléatoires
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Décommenter pour utiliser un backend distant (recommandé en production)
  # backend "s3" {
  #   bucket = "nexus-soc-tf-state"
  #   key    = "sovereign/terraform.tfstate"
  #   region = "eu-west-1"
  # }
  #
  # Pour un backend MinIO (cloud privé souverain) :
  # backend "s3" {
  #   bucket                      = "nexus-soc-tf-state"
  #   key                         = "sovereign/terraform.tfstate"
  #   region                      = "us-east-1"
  #   endpoint                    = "https://minio.votre-institution.cm"
  #   access_key                  = var.minio_access_key
  #   secret_key                  = var.minio_secret_key
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   skip_region_validation      = true
  #   force_path_style            = true
  # }
}

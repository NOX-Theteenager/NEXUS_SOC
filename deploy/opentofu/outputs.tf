# =============================================================================
# NEXUS SOC — Outputs du déploiement souverain
# Ces valeurs sont affichées après `tofu apply` et stockées dans le state.
# ATTENTION : les outputs sensitive=true ne s'affichent pas en clair dans le
# terminal mais restent dans le tfstate — chiffrer le state en production.
# =============================================================================

output "nexus_api_url" {
  description = "URL de l'API NEXUS SOC (scoring-service + endpoints admin/PLG)"
  value       = "http://${var.server_host}:8000"
}

output "nexus_api_docs" {
  description = "Documentation OpenAPI interactive"
  value       = "http://${var.server_host}:8000/docs"
}

output "wazuh_dashboard_url" {
  description = "Tableau de bord Wazuh (interface SIEM)"
  value       = "https://${var.server_host}:5601"
}

output "wazuh_api_url" {
  description = "API Wazuh Manager"
  value       = "https://${var.server_host}:55000"
}

output "nexus_console_note" {
  description = "Accès à la console fournisseur NEXUS SOC"
  value       = "Ouvrir Lot7_Console_Fournisseur/console_fournisseur.html dans un navigateur"
}

output "institution_name" {
  description = "Nom de l'institution souveraine déployée"
  value       = var.institution_name
}

output "install_directory" {
  description = "Répertoire d'installation sur le serveur"
  value       = var.install_dir
}

output "tls_certificate_pem" {
  description = "Certificat TLS auto-signé (à importer dans les navigateurs de l'institution)"
  value       = tls_self_signed_cert.nexus.cert_pem
  sensitive   = false  # Le certificat public peut être partagé
}

output "tls_cert_expiry" {
  description = "Date d'expiration du certificat TLS"
  value       = tls_self_signed_cert.nexus.validity_end_time
}

output "postgres_password" {
  description = "Mot de passe PostgreSQL (stocker dans un coffre-fort de secrets)"
  value       = local.pg_pass
  sensitive   = true
}

output "jwt_secret" {
  description = "Secret JWT (ne jamais exposer, stocker dans un coffre-fort)"
  value       = local.jwt_secret
  sensitive   = true
}

output "wazuh_admin_password" {
  description = "Mot de passe admin Wazuh"
  value       = local.wazuh_pass
  sensitive   = true
}

output "deployment_summary" {
  description = "Résumé du déploiement pour la documentation technique"
  value = {
    institution       = var.institution_name
    domain            = var.nexus_domain
    server            = var.server_host
    install_dir       = var.install_dir
    kafka_version     = var.kafka_version
    timescale_version = var.timescale_version
    wazuh_version     = var.wazuh_version
    nexus_version     = var.nexus_version
    plg_enabled       = var.enable_plg_module
    tls_expiry        = tls_self_signed_cert.nexus.validity_end_time
  }
}

output "next_steps" {
  description = "Instructions post-déploiement"
  value = <<-EOT

  ╔══════════════════════════════════════════════════════════════╗
  ║          NEXUS SOC — Déploiement Souverain Terminé          ║
  ╚══════════════════════════════════════════════════════════════╝

  1. VÉRIFIER LA SANTÉ DE LA PILE
     ssh ${var.server_user}@${var.server_host} 'cd ${var.install_dir} && docker compose ps'
     curl http://${var.server_host}:8000/health/detailed | python3 -m json.tool

  2. INSTALLER LES MODÈLES IA (si non uploadés)
     # Sur votre machine locale :
     scp model1_isoforest.joblib ${var.server_user}@${var.server_host}:${var.install_dir}/models/
     scp model2_isoforest.joblib ${var.server_user}@${var.server_host}:${var.install_dir}/models/
     # Redémarrer le service de scoring :
     ssh ${var.server_user}@${var.server_host} 'cd ${var.install_dir} && docker compose restart scoring-service'

  3. ENRÔLER LE PREMIER AGENT (depuis la console fournisseur)
     - Ouvrir : Lot7_Console_Fournisseur/console_fournisseur.html
     - Créer le tenant : ${var.institution_name}
     - Générer un token de provisioning
     - Copier le one-liner curl | bash sur les postes à surveiller

  4. ACCÉDER AUX INTERFACES
     API NEXUS SOC  : http://${var.server_host}:8000/docs
     Wazuh Dashboard: https://${var.server_host}:5601  (admin / [voir wazuh_admin_password])
     Console opér.  : ouvrir console_fournisseur.html en local

  5. CHANGER LES MOTS DE PASSE PAR DÉFAUT
     tofu output -raw postgres_password     # PostgreSQL
     tofu output -raw jwt_secret            # API JWT
     tofu output -raw wazuh_admin_password  # Wazuh

  6. CONFORMITÉ ANTIC
     - Déclarer le système auprès de l'ANTIC (www.antic.cm)
     - Fournir : architecture technique, politique de sécurité, PIA
  EOT
}

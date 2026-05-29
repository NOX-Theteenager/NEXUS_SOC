package main

// Variables injectées à la compilation par le service build_agent.py via ldflags :
//
//	go build -ldflags="-X 'main.TenantID=<uuid>'
//	                    -X 'main.WatermarkKey=<hmac-hex>'
//	                    -X 'main.WatermarkSalt=<salt-hex>'
//	                    -X 'main.ServerURL=https://nexussoc.cm'
//	                    -X 'main.AgentVersion=1.0.0'"
//
// Avec garble, ces constantes sont obfusquées dans le binaire final,
// rendant l'extraction statique difficile sans déboguer le processus.
// Le WatermarkKey est vérifiable côté serveur via HMAC-SHA256(master_key, TenantID:WatermarkSalt).

var (
	TenantID      = "00000000-0000-0000-0000-000000000000" // remplacé au build
	WatermarkKey  = "NEXUS_DEVELOPMENT_BUILD"              // HMAC hex injecté
	WatermarkSalt = "0000000000000000"                     // sel aléatoire unique
	ServerURL     = "https://nexussoc.cm"
	AgentVersion  = "1.0.0"
)

// WatermarkHeader retourne la valeur du header X-Nexus-Watermark à envoyer
// avec chaque lot de télémétrie. Permet au serveur de vérifier l'intégrité
// du binaire et d'associer l'agent à son tenant sans stocker de secret en dur.
func WatermarkHeader() string {
	return WatermarkKey[:16] // les 16 premiers caractères hex suffisent comme empreinte
}

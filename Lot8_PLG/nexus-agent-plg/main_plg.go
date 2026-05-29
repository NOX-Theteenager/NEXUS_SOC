package main

// main_plg.go — Points d'intégration PLG dans le main de l'agent
//
// Ce fichier n'est PAS un main() autonome. Il expose InitPLG() que le
// main.go original appelle après avoir chargé config.json.
//
// Flux de démarrage modifié :
//   1. main.go charge config.json (credentials minimalistes)
//   2. main.go appelle InitPLG(cfg) → récupère la config distante
//   3. La config distante enrichit le Config struct (watch_dirs, interval_sec)
//   4. Le reste de main.go démarre les collecteurs et le sender normalement
//
// Intégration dans main.go existant :
//   Ajouter après le chargement de config.json :
//     if err := InitPLG(&cfg); err != nil {
//         log.Fatalf("PLG init failed: %v", err)
//     }
//     defer ShutdownPLG()

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

// PLGState conserve l'état du sous-système PLG.
type PLGState struct {
	RemoteCfg *RemoteConfig
	stopCh    chan struct{}
}

var plgState *PLGState

// InitPLG initialise le sous-système PLG et enrichit le Config avec les règles distantes.
// Appelé une seule fois au démarrage, avant les collecteurs.
func InitPLG(cfg *Config) error {
	remote, err := InitConfigFetcher(cfg)
	if err != nil {
		return fmt.Errorf("config_fetcher init: %w", err)
	}

	// Appliquer la configuration distante sur le Config local
	applyRemoteConfig(cfg, remote)

	// Démarrer le refresh périodique
	StartConfigRefreshLoop(cfg)

	plgState = &PLGState{
		RemoteCfg: remote,
		stopCh:    make(chan struct{}),
	}

	// Gestion du signal SIGHUP : recharge la config à la demande
	go watchSignals(cfg)

	fmt.Printf("[PLG] Agent initialized | tenant=%s | version=%s | trial=%v\n",
		TenantID[:8], AgentVersion, remote.TrialActive)
	fmt.Printf("[PLG] Watch dirs: %v\n", cfg.WatchDirs)
	fmt.Printf("[PLG] Interval  : %ds\n", cfg.IntervalSec)

	return nil
}

// ShutdownPLG arrête proprement le sous-système PLG.
func ShutdownPLG() {
	if plgState != nil && plgState.stopCh != nil {
		close(plgState.stopCh)
	}
}

// applyRemoteConfig surcharge les champs de cfg avec les valeurs distantes.
// Les champs sensibles (ServerURL, EnrollToken, HMACKey) ne sont jamais écrasés.
func applyRemoteConfig(cfg *Config, rc *RemoteConfig) {
	if len(rc.WatchDirs) > 0 {
		cfg.WatchDirs = rc.WatchDirs
	}
	if rc.IntervalSec > 0 {
		cfg.IntervalSec = rc.IntervalSec
	}
	if rc.MaxQueueMB > 0 {
		cfg.QueueMaxMB = rc.MaxQueueMB
	}
}

// watchSignals recharge la configuration au signal SIGHUP.
func watchSignals(cfg *Config) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGHUP)
	for {
		select {
		case <-sigCh:
			fmt.Println("[PLG] SIGHUP received — refreshing remote config")
			remote, err := fetchRemoteConfig(cfg)
			if err != nil {
				fmt.Printf("[PLG] WARN config refresh failed: %v\n", err)
				continue
			}
			applyRemoteConfig(cfg, remote)
			fmt.Printf("[PLG] Config reloaded, version=%s\n", remote.ConfigVersion)
		case <-plgState.stopCh:
			return
		}
	}
}

// InjectWatermarkHeader ajoute le header X-Nexus-Watermark à chaque lot envoyé.
// Appelé depuis sender.go avant l'envoi HTTP.
func InjectWatermarkHeader(headers map[string]string) {
	headers["X-Nexus-Watermark"] = WatermarkHeader()
	headers["X-Nexus-Tenant"]    = TenantID
	headers["X-Nexus-Version"]   = AgentVersion
}

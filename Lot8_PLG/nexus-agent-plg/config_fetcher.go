package main

// config_fetcher.go — Récupération dynamique de la configuration agent
//
// L'agent est une "coquille vide" : config.json ne contient que les
// credentials minimaux (server_url, enroll_token, agent_id, tenant_id).
// Les règles de surveillance (watch_dirs, interval_sec, quotas) sont
// récupérées depuis l'API /plg/agent/config/{agent_id} au démarrage,
// puis mises en cache localement (chiffrement HMAC-SHA256) pour fonctionner
// en mode dégradé si le serveur est momentanément injoignable.

import (
	"bytes"
	"compress/gzip"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// RemoteConfig est la configuration reçue de l'API serveur.
type RemoteConfig struct {
	AgentID         string   `json:"agent_id"`
	TenantIDServer  string   `json:"tenant_id"`
	IntervalSec     int      `json:"interval_sec"`
	WatchDirs       []string `json:"watch_dirs"`
	MaxQueueMB      int      `json:"max_queue_mb"`
	TrialActive     bool     `json:"trial_active"`
	MaxAgents       int      `json:"max_agents"`
	MaxDailyEvents  int      `json:"max_daily_events"`
	ConfigVersion   string   `json:"config_version"`
	IssuedAt        string   `json:"issued_at"`
	Signature       string   `json:"signature"` // HMAC-SHA256 signé par le serveur
}

// ConfigCache gère le cache persistant de la configuration distante.
type ConfigCache struct {
	mu        sync.RWMutex
	current   *RemoteConfig
	cacheFile string
	hmacKey   string
}

var globalCache = &ConfigCache{}

// InitConfigFetcher initialise le cache et tente une première récupération.
// Retourne la config utilisable (distante ou cache) ou une erreur fatale.
func InitConfigFetcher(cfg *Config) (*RemoteConfig, error) {
	globalCache.cacheFile = filepath.Join(filepath.Dir(cfg.QueueDir), ".nexus_cfg_cache")
	globalCache.hmacKey   = cfg.HMACKey

	// Tentative de récupération distante
	remote, err := fetchRemoteConfig(cfg)
	if err == nil {
		globalCache.mu.Lock()
		globalCache.current = remote
		globalCache.mu.Unlock()
		_ = persistCache(remote, cfg.HMACKey, globalCache.cacheFile)
		return remote, nil
	}

	logWarn("config_fetcher: remote unavailable (%v), falling back to cache", err)

	// Fallback sur le cache local
	cached, cacheErr := loadCache(cfg.HMACKey, globalCache.cacheFile)
	if cacheErr != nil {
		return nil, fmt.Errorf("no remote config and no valid cache: %w", cacheErr)
	}

	logWarn("config_fetcher: using cached config version=%s issued=%s",
		cached.ConfigVersion, cached.IssuedAt)

	globalCache.mu.Lock()
	globalCache.current = cached
	globalCache.mu.Unlock()
	return cached, nil
}

// StartConfigRefreshLoop lance un goroutine qui rafraîchit la config toutes les 5 minutes.
func StartConfigRefreshLoop(cfg *Config) {
	go func() {
		ticker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()
		for range ticker.C {
			remote, err := fetchRemoteConfig(cfg)
			if err != nil {
				logWarn("config_fetcher: refresh failed: %v", err)
				continue
			}
			globalCache.mu.Lock()
			globalCache.current = remote
			globalCache.mu.Unlock()
			_ = persistCache(remote, cfg.HMACKey, globalCache.cacheFile)
			logInfo("config_fetcher: config refreshed, version=%s", remote.ConfigVersion)
		}
	}()
}

// CurrentConfig retourne la config active (thread-safe).
func CurrentConfig() *RemoteConfig {
	globalCache.mu.RLock()
	defer globalCache.mu.RUnlock()
	return globalCache.current
}

// =============================================================================
// Fonctions internes
// =============================================================================

func fetchRemoteConfig(cfg *Config) (*RemoteConfig, error) {
	url := fmt.Sprintf("%s/plg/agent/config/%s", cfg.ServerURL, cfg.AgentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+cfg.EnrollToken)
	req.Header.Set("X-Nexus-Watermark", WatermarkHeader())
	req.Header.Set("User-Agent", fmt.Sprintf("nexus-agent/%s", AgentVersion))

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("HTTP error: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusPaymentRequired {
		return nil, fmt.Errorf("tenant suspended or trial expired (HTTP 402)")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	var rc RemoteConfig
	if err := json.Unmarshal(body, &rc); err != nil {
		return nil, fmt.Errorf("JSON parse: %w", err)
	}

	// Vérifier la signature HMAC envoyée par le serveur
	if !verifyServerSignature(&rc) {
		return nil, fmt.Errorf("invalid server signature — config rejected")
	}

	return &rc, nil
}

// verifyServerSignature vérifie que la config n'a pas été altérée en transit.
// Le serveur signe le corps JSON trié avec JWT_SECRET (partagé).
func verifyServerSignature(rc *RemoteConfig) bool {
	sig := rc.Signature
	rc.Signature = "" // exclure la signature elle-même du calcul
	defer func() { rc.Signature = sig }()

	body, err := json.Marshal(rc) // pas sort_keys en Go, mais le serveur envoie sorted
	if err != nil {
		return false
	}

	// La clé de vérification est la clé HMAC de l'agent (injectée à la compilation)
	mac := hmac.New(sha256.New, []byte(WatermarkKey))
	mac.Write(body)
	expected := hex.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(expected), []byte(sig))
}

// =============================================================================
// Cache persistant chiffré par HMAC
// =============================================================================

func persistCache(rc *RemoteConfig, hmacKey, path string) error {
	data, err := json.Marshal(rc)
	if err != nil {
		return err
	}

	// Compression gzip
	var buf bytes.Buffer
	w := gzip.NewWriter(&buf)
	_, _ = w.Write(data)
	_ = w.Close()
	compressed := buf.Bytes()

	// Calcul du tag HMAC pour détecter toute altération du fichier cache
	mac := hmac.New(sha256.New, []byte(hmacKey))
	mac.Write(compressed)
	tag := mac.Sum(nil)

	// Format : [32 bytes HMAC tag][gzip payload]
	out := append(tag, compressed...)
	return os.WriteFile(path, out, 0600)
}

func loadCache(hmacKey, path string) (*RemoteConfig, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if len(raw) < 32 {
		return nil, fmt.Errorf("cache file too short")
	}

	tag       := raw[:32]
	compressed := raw[32:]

	// Vérifier l'intégrité
	mac := hmac.New(sha256.New, []byte(hmacKey))
	mac.Write(compressed)
	if !hmac.Equal(tag, mac.Sum(nil)) {
		_ = os.Remove(path) // cache altéré : supprimer
		return nil, fmt.Errorf("cache HMAC mismatch — tampered file removed")
	}

	// Décompression
	r, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		return nil, err
	}
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, err
	}

	var rc RemoteConfig
	if err := json.Unmarshal(data, &rc); err != nil {
		return nil, err
	}
	return &rc, nil
}

// logInfo et logWarn sont des stubs : l'agent principal les fournit via logger global.
func logInfo(format string, args ...interface{}) {
	fmt.Printf("[INFO] "+format+"\n", args...)
}
func logWarn(format string, args ...interface{}) {
	fmt.Printf("[WARN] "+format+"\n", args...)
}

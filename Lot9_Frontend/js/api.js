/**
 * NEXUS SOC — Client API universel
 * Gère : JWT (access + refresh), auto-refresh sur 401, tous les endpoints,
 * guard de route, polling temps réel.
 *
 * Usage : inclure avant tout autre script via <script src="js/api.js"></script>
 * Expose : window.NexusAPI (instance singleton)
 */
(function (window) {
  'use strict';

  // ─── Configuration ─────────────────────────────────────────────────────────

  /** Base URL de l'API. Vide = même origine (production).
   *  En dev, si ouvert depuis file:// ou port différent, pointe vers :8000 */
  const BASE =
    window.location.protocol === 'file:' ||
    (window.location.hostname === 'localhost' && window.location.port !== '8000')
      ? 'http://localhost:8000'
      : '';

  const STORAGE = {
    ACCESS:  'nexus_access_token',
    REFRESH: 'nexus_refresh_token',
    USER:    'nexus_user',
  };

  // ─── Classe principale ─────────────────────────────────────────────────────

  class NexusAPIClient {
    constructor() {
      this._accessToken  = null;
      this._refreshToken = null;
      this._user         = null;
      this._listeners    = {};  // event bus interne
    }

    // ── Getters ──────────────────────────────────────────────────────────────

    get accessToken() {
      if (!this._accessToken)
        this._accessToken = localStorage.getItem(STORAGE.ACCESS);
      return this._accessToken;
    }

    get user() {
      if (!this._user) {
        const raw = localStorage.getItem(STORAGE.USER);
        try { if (raw) this._user = JSON.parse(raw); } catch {}
      }
      return this._user;
    }

    get isAuthenticated() { return !!this.accessToken; }
    get role()            { return this.user?.role || null; }
    get tenantId()        { return this.user?.tenant_id || null; }

    // ── Guard ────────────────────────────────────────────────────────────────

    /** Redirige vers login.html si non authentifié ou mauvais rôle.
     *  @param {string|string[]} [roles] - rôles autorisés (optionnel)
     *  @returns {boolean} true si accès autorisé */
    guard(roles = null) {
      if (!this.isAuthenticated) {
        window.location.href = 'login.html';
        return false;
      }
      if (roles) {
        const allowed = Array.isArray(roles) ? roles : [roles];
        if (!allowed.includes(this.role)) {
          window.location.href = 'login.html';
          return false;
        }
      }
      return true;
    }

    // ── Requête HTTP centrale ─────────────────────────────────────────────────

    async _req(method, path, body = null, _retry = true) {
      const headers = { 'Content-Type': 'application/json' };
      if (this.accessToken) headers['Authorization'] = `Bearer ${this.accessToken}`;

      const opts = { method, headers };
      if (body) opts.body = JSON.stringify(body);

      let res;
      try {
        res = await fetch(BASE + path, opts);
      } catch (networkErr) {
        throw { status: 0, detail: 'Erreur réseau — serveur injoignable.', _network: true };
      }

      // Auto-refresh sur 401
      if (res.status === 401 && _retry) {
        const refreshed = await this._doRefresh();
        if (refreshed) return this._req(method, path, body, false);
        this.logout(false);
        return null;
      }

      if (res.status === 204) return null; // No Content

      let data;
      try { data = await res.json(); }
      catch { data = { detail: res.statusText }; }

      if (!res.ok) {
        const msg = typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail || data);
        throw { status: res.status, detail: msg };
      }

      return data;
    }

    /** Alias par méthode HTTP */
    get(path)         { return this._req('GET',    path); }
    post(path, body)  { return this._req('POST',   path, body); }
    put(path, body)   { return this._req('PUT',    path, body); }
    patch(path, body) { return this._req('PATCH',  path, body); }
    del(path)         { return this._req('DELETE', path); }

    // ── Refresh token ─────────────────────────────────────────────────────────

    async _doRefresh() {
      const rt = localStorage.getItem(STORAGE.REFRESH);
      if (!rt) return false;
      try {
        const r = await fetch(BASE + '/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        });
        if (!r.ok) return false;
        const d = await r.json();
        this._accessToken = d.access_token;
        localStorage.setItem(STORAGE.ACCESS, d.access_token);
        return true;
      } catch { return false; }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // ENDPOINTS
    // ─────────────────────────────────────────────────────────────────────────

    // ── Auth ─────────────────────────────────────────────────────────────────

    async login(email, password) {
      const d = await this._req('POST', '/auth/token', { email, password });
      if (!d) return null;
      this._accessToken = d.access_token;
      localStorage.setItem(STORAGE.ACCESS,  d.access_token);
      localStorage.setItem(STORAGE.REFRESH, d.refresh_token || '');
      // Récupère le profil et le stocke
      try {
        const me = await this._req('GET', '/auth/me');
        if (me) {
          this._user = me;
          localStorage.setItem(STORAGE.USER, JSON.stringify(me));
        }
      } catch {}
      return d;
    }

    async me() { return this.get('/auth/me'); }

    logout(redirect = true) {
      [STORAGE.ACCESS, STORAGE.REFRESH, STORAGE.USER].forEach(k =>
        localStorage.removeItem(k));
      this._accessToken = this._refreshToken = this._user = null;
      if (redirect) window.location.href = 'login.html';
    }

    // ── Admin — Tenants ───────────────────────────────────────────────────────

    getTenants()           { return this.get('/admin/tenants'); }
    getTenant(id)          { return this.get(`/admin/tenants/${id}`); }
    createTenant(data)     { return this.post('/admin/tenants', data); }
    // Le backend expose PATCH (mise à jour partielle), pas PUT.
    updateTenant(id, data) { return this.patch(`/admin/tenants/${id}`, data); }
    suspendTenant(id)      { return this.post(`/admin/tenants/${id}/suspend`); }
    activateTenant(id)     { return this.post(`/admin/tenants/${id}/activate`); }
    deleteTenant(id)       { return this.del(`/admin/tenants/${id}`); }

    // ── Admin — Users ─────────────────────────────────────────────────────────

    getUsers(params = {})  {
      const qs = new URLSearchParams(params).toString();
      return this.get(`/admin/users${qs ? '?' + qs : ''}`);
    }
    createUser(data)       { return this.post('/admin/users', data); }
    updateUser(id, data)   { return this.put(`/admin/users/${id}`, data); }
    deleteUser(id)         { return this.del(`/admin/users/${id}`); }

    // ── Admin — Agents ────────────────────────────────────────────────────────

    getAgents(params = {}) {
      const qs = new URLSearchParams(params).toString();
      return this.get(`/admin/agents${qs ? '?' + qs : ''}`);
    }

    // ── Admin — Health & Périmètres ───────────────────────────────────────────

    getHealth()            { return this.get('/health/detailed'); }
    getHealthSimple()      { return this.get('/health'); }
    getPerimetres()        { return this.get('/admin/perimetres'); }
    getMetrics(hours=24)   { return this.get(`/admin/metrics?hours=${hours}`); }
    getModelDrift(days=7)  { return this.get(`/monitor/drift?days=${days}`); }

    // ── Provisioning ──────────────────────────────────────────────────────────

    generateToken(data)           { return this.post('/provision/token', data); }
    getTokenStatus(id)            { return this.get(`/provision/status/${id}`); }
    getEnrollmentLog(id)          { return this.get(`/provision/status/${id}/log`); }
    revokeToken(id)               { return this.post(`/provision/revoke/${id}`); }
    revokeAllAgents(tenantId)     { return this.post(`/provision/revoke-tenant/${tenantId}`); }
    rotateHmac(agentId)           { return this.post(`/provision/rotate-hmac/${agentId}`); }
    /** Isole (ou reconnecte) un lot d'agents. L'isolement coupe l'ingestion à
     *  la source ; il ne confine pas la machine sur le réseau. */
    bulkAgentIsolation(agentIds, isoler, motif = null) {
      return this.post('/admin/agents/isolation',
                       { agent_ids: agentIds, isoler, motif });
    }
    getInstaller(id, os)          { return this.get(`/provision/installer/${id}?os=${os}`); }
    getQrCode(agentId, bearer = '') {
      const qs = new URLSearchParams({ bearer }).toString();
      return this.get(`/provision/qr/${agentId}?${qs}`);
    }

    /** Commande shell à copier telle quelle sur le poste cible.
     *  Chaîne construite côté client : aucun appel réseau, donc affichable
     *  immédiatement après la génération du jeton. */
    getOneliner(token, hostname, os = 'linux') {
      const origin = BASE || window.location.origin;
      const url = `${origin}/provision/oneliner?token=${encodeURIComponent(token)}`
                + `&hostname=${encodeURIComponent(hostname)}&os=${os}`;
      return os === 'windows'
        ? `irm "${url}" | iex`
        : `curl -fsSL "${url}" | sudo sh`;
    }

    /** Téléchargements authentifiés (Bearer) : le navigateur ne peut pas
     *  poser l'en-tête sur un <a download>, on passe donc par un blob. */
    downloadInstaller(agentId, os, bearer = '', hmac = '') {
      const qs = new URLSearchParams({ os, bearer, hmac }).toString();
      return this._download(`/provision/installer/${agentId}?${qs}`,
        os === 'windows' ? `Install-NexusAgent.ps1` : `install_nexus_agent.sh`);
    }
    downloadOfflinePack(agentId, os = 'linux', bearer = '', hmac = '') {
      const qs = new URLSearchParams({ os, bearer, hmac }).toString();
      return this._download(`/provision/offline-pack/${agentId}?${qs}`,
        `nexus-agent-${String(agentId).slice(0, 4)}.zip`);
    }

    async _download(path, filename) {
      const r = await fetch(BASE + path, {
        headers: { 'Authorization': `Bearer ${this.accessToken}` },
      });
      if (!r.ok) throw { status: r.status, detail: 'Téléchargement refusé' };
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    /** Enrôlement en masse : l'endpoint attend un multipart avec un vrai
     *  fichier CSV (hostname,os,description), pas un corps JSON. */
    async bulkProvision(tenantId, file, expiresInHours = 24) {
      const qs = new URLSearchParams({
        tenant_id: tenantId, expires_in_hours: expiresInHours,
      }).toString();
      const fd = new FormData();
      fd.append('file', file, file.name || 'parc.csv');
      const r = await fetch(`${BASE}/provision/bulk?${qs}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${this.accessToken}` },
        body: fd,
      });
      const data = await r.json().catch(() => ({ detail: r.statusText }));
      if (!r.ok) throw { status: r.status, detail: data.detail || r.statusText };
      return data;
    }

    // ── Analyst — Alertes ─────────────────────────────────────────────────────

    getAlerts(params = {}) {
      const qs = new URLSearchParams(params).toString();
      return this.get(`/analyst/alerts${qs ? '?' + qs : ''}`);
    }
    getAlert(id)           { return this.get(`/analyst/alerts/${id}`); }
    approveAction(actionId, approvedBy) {
      return this.post(`/analyst/approve/${actionId}`, { approved_by: approvedBy });
    }
    rejectAction(actionId, reason) {
      return this.post(`/analyst/reject/${actionId}`, { reason });
    }
    /** Déclare qu'un opérateur a réellement passé la commande à la main.
     *  Approuver n'exécute rien tant qu'aucun connecteur n'est raccordé :
     *  c'est cet appel, nominatif et horodaté, qui atteste l'exécution. */
    markActionExecuted(actionId, executedBy, note) {
      return this.post(`/analyst/executed/${actionId}`, { executed_by: executedBy, note });
    }
    markFalsePositive(alertId) {
      return this.post(`/analyst/false-positive/${alertId}`);
    }
    getSOCDashboard()      { return this.get('/analyst/dashboard'); }
    getPendingSOAR()       { return this.get('/analyst/pending'); }

    /** Journal d'audit SOAR — qui a fait quoi, quand, sur quelle décision. */
    getSoarAudit(params = {}) {
      const clean = Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== '' && v != null));
      const qs = new URLSearchParams(clean).toString();
      return this.get(`/analyst/soar-audit${qs ? '?' + qs : ''}`);
    }

    // ── Demandes internes (contact.html) ──────────────────────────────────────

    requestPerimetre(data) { return this.post('/contact/perimetre-request', data); }

    // ── Scoring ───────────────────────────────────────────────────────────────

    scoreNetwork(features)  { return this.post('/score/network',   { features }); }
    scoreUserDay(features)  { return this.post('/score/user-day',  { features }); }

    // ── Portail DSI (vue restreinte au tenant du JWT) ─────────────────────────

    getPortalAlerts(limit = 50) { return this.get(`/portal/alerts?limit=${limit}`); }
    getPortalAgents()           { return this.get('/portal/agents'); }
    getPortalSummary()          { return this.get('/portal/summary'); }

    /** Explication d'un incident en langage clair, produite par le serveur
     *  (module Analyst du Lot 5). Mode template par défaut, LLM si configuré. */
    explainAlert(alertId, lang = 'fr') {
      return this.get(`/portal/alerts/${alertId}/explain?lang=${lang}`);
    }
    getPortalNotifications(unreadOnly = false, limit = 50) {
      const qs = new URLSearchParams({ unread_only: unreadOnly, limit }).toString();
      return this.get(`/portal/notifications?${qs}`);
    }
    markNotifRead(id)           { return this.post(`/portal/notifications/${id}/mark-read`); }
    markAllNotifsRead()         { return this.post('/portal/notifications/mark-all-read'); }
    /** Le rapport suit la langue de la page. La version française est celle
     *  figée en base au moment de l'incident ; les autres sont rendues à la
     *  demande depuis les mêmes données. */
    /** Historique du score, agrégé côté serveur. Les jours sans télémétrie
     *  reviennent avec `score: null` — ce sont des jours sans information, pas
     *  des jours sans incident. */
    getScoreHistory(days = 14) { return this.get(`/portal/score-history?days=${days}`); }

    /** Historique complet des rapports du périmètre, pas seulement le dernier. */
    getReportHistory(limit = 50) { return this.get(`/portal/reports?limit=${limit}`); }

    /** Le responsable DEMANDE l'isolation ; un analyste la valide. La demande
     *  entre dans la file SOAR, elle n'exécute rien. */
    requestIsolation(alertId, motif = null) {
      return this.post(`/portal/alerts/${alertId}/request-isolation`, { motif });
    }

    getNotifReport(id, lang = 'fr') {
      return this.get(`/portal/notifications/${id}/report?lang=${encodeURIComponent(lang)}`);
    }

    /** Télécharge le rapport HTML authentifié (Bearer) sous forme de blob.
     *  Déclenche un download navigateur avec un nom de fichier propre. */
    async downloadNotifReport(id, filename = null, lang = 'fr') {
      const r = await fetch(BASE + `/portal/notifications/${id}/download?lang=${encodeURIComponent(lang)}`, {
        headers: { 'Authorization': `Bearer ${this.accessToken}` },
      });
      if (!r.ok) throw { status: r.status, detail: 'Téléchargement refusé' };
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename
        || `rapport-nexussoc-${id.slice(0, 8)}${lang !== 'fr' ? '-' + lang : ''}.html`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // UTILITAIRES UI
    // ─────────────────────────────────────────────────────────────────────────

    /** Polling : appelle fn toutes les intervalMs ms.
     *  Retourne une fonction stop() pour annuler.
     *  @param {Function} fn - fonction async à appeler
     *  @param {number} [intervalMs=30000]
     *  @returns {Function} stop
     */
    poll(fn, intervalMs = 30_000) {
      fn();
      const id = setInterval(fn, intervalMs);
      return () => clearInterval(id);
    }

    /** Formatage date locale */
    formatDate(iso, lang = 'fr') {
      if (!iso) return '—';
      return new Date(iso).toLocaleString(lang === 'fr' ? 'fr-CM' : 'en-US', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    }

    /** Couleur de risque (0–100) */
    riskColor(score) {
      if (score >= 80) return 'var(--red)';
      if (score >= 60) return 'var(--amber)';
      if (score >= 40) return 'var(--accent)';
      return 'var(--teal)';
    }

    /** Badge de criticité d'un périmètre supervisé */
    criticiteBadge(criticite) {
      const map = {
        critique: { label: 'Critique', color: 'var(--red)' },
        sensible: { label: 'Sensible', color: 'var(--amber)' },
        standard: { label: 'Standard', color: 'var(--accent)' },
        none:     { label: '—',        color: 'var(--text-3)' },
      };
      return map[criticite] || map.none;
    }
  }

  // ─── Singleton global ─────────────────────────────────────────────────────

  window.NexusAPI = new NexusAPIClient();

})(window);

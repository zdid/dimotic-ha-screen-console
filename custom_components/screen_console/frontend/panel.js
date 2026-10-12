/* Console screen pour Home Assistant — panneau personnalisé (Dimotic-HA Screen Console).
 * Terminal xterm.js relié à une session `screen` de la machine hôte par les commandes WebSocket de
 * l'intégration `screen_console` (réservées aux administrateurs de HA).
 * Fonctionne dans le navigateur et dans l'application mobile HA (Android / iOS : même moteur web). */
(() => {
  const BASE = new URL('.', import.meta.url).pathname; // /screen_console_static/
  const LAST_SESSION_KEY = 'screen_console:last_session';

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = src; el.onload = () => resolve(); el.onerror = () => reject(new Error('Chargement impossible : ' + src));
      document.head.appendChild(el);
    });
  }
  async function ensureXterm() {
    if (!window.Terminal) await loadScript(BASE + 'xterm.js');
    if (!window.FitAddon) await loadScript(BASE + 'addon-fit.js');
  }
  const b64 = (bytes) => { let s = ''; for (const b of bytes) s += String.fromCharCode(b); return btoa(s); };
  const unb64 = (str) => Uint8Array.from(atob(str), (c) => c.charCodeAt(0));
  const utf8 = (text) => new TextEncoder().encode(text);

  /* Rapports de souris : par défaut TOUS sont retirés (mouvements, clics, molette) — le programme distant
   * (ex. Claude Code dans screen) ne les comprend pas et en laissait la fin dans la saisie (« 60;46m »).
   * Avec « Souris : oui », seuls les MOUVEMENTS (bit 32) sont retirés ; clics et molette sont transmis. */
  const SGR = /\x1b\[<(\d+);\d+;\d+[Mm]/g;
  const X10 = /\x1b\[M([\s\S])[\s\S][\s\S]/g;
  function filterMouse(data, forward) {
    if (!forward) return data.replace(SGR, '').replace(X10, '');
    return data
      .replace(SGR, (m, b) => ((parseInt(b, 10) & 32) !== 0 ? '' : m))
      .replace(X10, (m, c) => ((((c.charCodeAt(0) - 32) & 32) !== 0) ? '' : m));
  }

  /* Séquences des touches de la barre : \x01 = Ctrl-A, \x1b = Échap. */
  function expand(seq) { return seq.replace(/\\x([0-9a-fA-F]{2})/g, (_m, h) => String.fromCharCode(parseInt(h, 16))); }

  const KEYS = [
    ['Défiler', '\\x01\\x1b', 'Mode défilement de screen (Ctrl-A puis Échap)'],
    ['↑', '\\x1b[A', 'Ligne précédente'],
    ['↓', '\\x1b[B', 'Ligne suivante'],
    ['Page ↑', '\\x02', 'Page précédente (Ctrl-B)'],
    ['Page ↓', '\\x06', 'Page suivante (Ctrl-F)'],
    ['Échap', '\\x1b', 'Quitter le mode défilement'],
    ['Tab', '\\x09', 'Tabulation'],
    ['Ctrl-C', '\\x03', 'Interrompre']
  ];

  const STYLE = `
    :host { display: flex; flex-direction: column; height: 100vh; height: 100dvh; background: #111; color: #fff; font-family: Arial, sans-serif; overflow: hidden; }
    .top { flex: none; display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; padding: 4px 8px; background: #222; min-height: 48px; }
    .title { font-weight: bold; }
    .status { color: #aaa; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .status.ok { color: #6c6; } .status.err { color: #e66; }
    .actions { margin-left: auto; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; min-width: 0; }
    select, button { height: 32px; border-radius: 4px; border: 1px solid #555; background: #333; color: #fff; font-size: 14px; padding: 0 10px; }
    select { min-width: 0; max-width: 100%; } button { cursor: pointer; touch-action: manipulation; }
    button:disabled { opacity: .45; cursor: not-allowed; } button:active { background: #555; }
    .keys { flex: none; display: flex; gap: 6px; padding: 4px 8px; background: #1b1b1b; overflow-x: auto; }
    .keys button { flex: 1 0 auto; height: 36px; }
    .term { flex: 1; min-height: 0; padding: 2px; } .term .xterm { height: 100%; }
    .hint { padding: 12px; color: #ccc; font-size: 14px; white-space: pre-wrap; }
    .hint code { display: block; background: #000; padding: 8px; margin-top: 8px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
    ha-menu-button { --mdc-icon-button-size: 40px; }
  `;

  class ScreenConsolePanel extends HTMLElement {
    constructor() {
      super();
      this._hass = null; this._narrow = false; this._built = false;
      this._term = null; this._fit = null; this._unsub = null; this._sessionId = null;
      this._mouse = localStorage.getItem('screen_console:mouse') === '1';
      this.attachShadow({ mode: 'open' });
    }
    set hass(hass) { this._hass = hass; if (!this._built) this._build(); this._menu && (this._menu.hass = hass); }
    set narrow(value) { this._narrow = value; this._menu && (this._menu.narrow = value); }
    set panel(_p) {} set route(_r) {}

    disconnectedCallback() { this._disconnect(true); this._ro && this._ro.disconnect(); }

    _build() {
      this._built = true;
      const root = this.shadowRoot;
      root.innerHTML = `<style>${STYLE}</style>
        <link rel="stylesheet" href="${BASE}xterm.css">
        <div class="top">
          <ha-menu-button></ha-menu-button>
          <span class="title">Console</span>
          <span class="status" id="status">Démarrage…</span>
          <div class="actions">
            <select id="sel" aria-label="Session screen"></select>
            <button id="refresh" title="Actualiser la liste">↻</button>
            <button id="connect">Connecter</button>
            <button id="disconnect" disabled>Déconnecter</button>
          </div>
        </div>
        <div class="keys" id="keys"></div>
        <div class="term" id="term"></div>`;
      this._menu = root.querySelector('ha-menu-button');
      this._menu.hass = this._hass; this._menu.narrow = this._narrow;
      this.$ = (id) => root.getElementById(id);
      const keys = this.$('keys');
      for (const [label, seq, title] of KEYS) {
        const b = document.createElement('button'); b.textContent = label; b.title = title;
        b.addEventListener('mousedown', (e) => e.preventDefault());
        b.addEventListener('click', () => this._send(expand(seq)));
        keys.appendChild(b);
      }
      const mb = document.createElement('button'); mb.id = 'mouse';
      const paintMouse = () => { mb.textContent = 'Souris : ' + (this._mouse ? 'oui' : 'non'); mb.title = this._mouse ? 'Clics et molette envoyés au programme distant' : 'Aucun clic ni molette envoyés (la molette fait défiler l\'historique local)'; };
      mb.addEventListener('mousedown', (e) => e.preventDefault());
      mb.addEventListener('click', () => { this._mouse = !this._mouse; localStorage.setItem('screen_console:mouse', this._mouse ? '1' : '0'); paintMouse(); });
      paintMouse(); keys.appendChild(mb);
      this.$('connect').addEventListener('click', () => this._connect());
      this.$('disconnect').addEventListener('click', () => this._disconnect(false));
      this.$('refresh').addEventListener('click', () => this._refresh());
      this._init();
    }

    _setStatus(text, cls) { const s = this.$('status'); s.textContent = text; s.className = 'status ' + (cls || ''); }

    async _init() {
      try {
        await ensureXterm();
        this._term = new window.Terminal({ cursorBlink: true, scrollback: 5000, fontSize: 14, theme: { background: '#000000' },
          fontFamily: 'Menlo, Consolas, "DejaVu Sans Mono", monospace' });
        this._fit = new window.FitAddon.FitAddon();
        this._term.loadAddon(this._fit);
        this._term.open(this.$('term'));
        this._term.onData((data) => { const out = filterMouse(data, this._mouse); if (out) this._send(out); });
        // Souris désactivée : la molette fait défiler l'historique local du terminal (rien n'est envoyé).
        this._term.attachCustomWheelEventHandler((e) => { if (this._mouse) return true; this._term.scrollLines(e.deltaY > 0 ? 3 : -3); return false; });
        this._term.onResize(() => this._sendResize());
        this._ro = new ResizeObserver(() => { try { this._fit.fit(); } catch (_e) { /* masqué */ } });
        this._ro.observe(this.$('term'));
        try { this._fit.fit(); } catch (_e) { /* idem */ }
      } catch (err) { this._setStatus(String(err), 'err'); return; }
      await this._refresh(true);
    }

    async _refresh(autoConnect) {
      this._setStatus('Recherche des sessions…');
      const sel = this.$('sel');
      try {
        const res = await this._hass.callWS({ type: 'screen_console/list' });
        const last = localStorage.getItem(LAST_SESSION_KEY);
        sel.innerHTML = '';
        for (const s of res.sessions) {
          const o = document.createElement('option'); o.value = s.name; o.textContent = `${s.name} (${s.state})`; sel.appendChild(o);
        }
        if (!res.sessions.length) { this._setStatus('Aucune session screen sur la machine.', 'err'); return; }
        // « claude » arrive en premier (tri côté serveur) ; on réutilise la dernière session choisie si elle existe encore.
        if (last && res.sessions.some((s) => s.name === last)) sel.value = last;
        this._setStatus('Prêt', '');
        if (autoConnect) this._connect();
      } catch (err) {
        this._showSetupHint(err);
      }
    }

    _showSetupHint(err) {
      const message = (err && err.message) || String(err);
      this._setStatus('Liste impossible', 'err');
      const term = this.$('term');
      const hint = document.createElement('div'); hint.className = 'hint';
      hint.textContent = message + '\n\nVérifiez que la clé de la console est autorisée sur la machine et que le script de contrôle est installé (voir le fichier README du dépôt dimotic-ha-screen-console).';
      term.appendChild(hint);
    }

    async _connect() {
      const name = this.$('sel').value; if (!name || this._unsub) return;
      localStorage.setItem(LAST_SESSION_KEY, name);
      this._term.reset();
      this._sessionId = 'c' + Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
      this._setStatus('Connexion à « ' + name + ' »…');
      this.$('connect').disabled = true; this.$('sel').disabled = true;
      try {
        this._unsub = await this._hass.connection.subscribeMessage(
          (event) => this._onEvent(event),
          { type: 'screen_console/connect', session_id: this._sessionId, name, cols: this._term.cols, rows: this._term.rows }
        );
        this._setStatus('Connecté : ' + name, 'ok');
        this.$('disconnect').disabled = false; this._term.focus();
      } catch (err) {
        this._unsub = null; this._sessionId = null;
        this._setStatus((err && err.message) || 'Connexion impossible', 'err');
        this.$('connect').disabled = false; this.$('sel').disabled = false;
      }
    }

    _onEvent(event) {
      if (event.type === 'output') this._term.write(unb64(event.data));
      else if (event.type === 'closed') { this._endLocal('Session ' + event.reason); }
    }

    _endLocal(message) {
      if (this._unsub) { try { this._unsub(); } catch (_e) { /* déjà fermé */ } }
      this._unsub = null; this._sessionId = null;
      this._setStatus(message, 'err');
      this.$('connect').disabled = false; this.$('sel').disabled = false; this.$('disconnect').disabled = true;
    }

    _disconnect(silent) {
      if (this._unsub) { try { this._unsub(); } catch (_e) { /* déjà fermé */ } }
      this._unsub = null; this._sessionId = null;
      if (!silent && this.$) {
        this._setStatus('Déconnecté', '');
        this.$('connect').disabled = false; this.$('sel').disabled = false; this.$('disconnect').disabled = true;
      }
    }

    _send(text) {
      if (!this._sessionId || !this._hass) return;
      this._hass.callWS({ type: 'screen_console/input', session_id: this._sessionId, data: b64(utf8(text)) }).catch(() => {});
    }
    _sendResize() {
      if (!this._sessionId || !this._term) return;
      this._hass.callWS({ type: 'screen_console/resize', session_id: this._sessionId, cols: this._term.cols, rows: this._term.rows }).catch(() => {});
    }
  }
  if (!customElements.get('screen-console-panel')) customElements.define('screen-console-panel', ScreenConsolePanel);
})();

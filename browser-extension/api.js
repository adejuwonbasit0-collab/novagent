// Mirrors dashboard/lib/api.ts's request/token patterns, adapted for
// chrome.storage.local instead of localStorage (extension popups don't
// share localStorage with any page, and chrome.storage is the correct
// primitive for extension-scoped persistent state).

const NovaAPI = (() => {
  // JS's Date.toISOString() always renders in UTC ("...Z") -- there's no
  // built-in for "local wall-clock time, with its own offset" the way
  // Python's datetime.now().astimezone().isoformat() gives for free.
  // Built from the local getters + getTimezoneOffset() instead.
  function localIsoWithOffset() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const offsetMin = -d.getTimezoneOffset(); // JS's sign is inverted vs. what we want
    const sign = offsetMin >= 0 ? "+" : "-";
    const abs = Math.abs(offsetMin);
    const offset = `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
    return (
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${offset}`
    );
  }

  async function getBackendUrl() {
    const { backendUrl } = await chrome.storage.local.get("backendUrl");
    return backendUrl || NOVA_CONFIG.DEFAULT_BACKEND_URL;
  }

  async function getTokens() {
    const { accessToken, refreshToken } = await chrome.storage.local.get(["accessToken", "refreshToken"]);
    return { accessToken, refreshToken };
  }

  async function setTokens(accessToken, refreshToken) {
    await chrome.storage.local.set({ accessToken, refreshToken });
  }

  async function clearTokens() {
    await chrome.storage.local.remove(["accessToken", "refreshToken"]);
  }

  async function isLoggedIn() {
    const { accessToken } = await getTokens();
    return !!accessToken;
  }

  async function request(method, path, { json, auth = true } = {}) {
    const backendUrl = await getBackendUrl();
    const headers = { "Content-Type": "application/json" };

    if (auth) {
      const { accessToken } = await getTokens();
      if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    }

    let resp = await fetch(`${backendUrl}${path}`, {
      method,
      headers,
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });

    if (resp.status === 401 && auth) {
      const refreshed = await tryRefresh();
      if (refreshed) {
        const { accessToken } = await getTokens();
        headers["Authorization"] = `Bearer ${accessToken}`;
        resp = await fetch(`${backendUrl}${path}`, {
          method,
          headers,
          body: json !== undefined ? JSON.stringify(json) : undefined,
        });
      }
    }

    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const body = await resp.json();
        detail = body.detail || detail;
      } catch {
        /* not JSON */
      }
      throw new Error(detail);
    }
    if (resp.status === 204) return undefined;
    return resp.json();
  }

  async function tryRefresh() {
    try {
      const { refreshToken } = await getTokens();
      if (!refreshToken) return false;
      const data = await request("POST", "/api/v1/auth/refresh", {
        json: { refresh_token: refreshToken },
        auth: false,
      });
      await setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      await clearTokens();
      return false;
    }
  }

  return {
    getBackendUrl,
    setBackendUrl: (url) => chrome.storage.local.set({ backendUrl: url }),
    isLoggedIn,
    async login(email, password) {
      const data = await request("POST", "/api/v1/auth/login", { json: { email, password }, auth: false });
      await setTokens(data.access_token, data.refresh_token);
    },
    logout: clearTokens,
    me: () => request("GET", "/api/v1/auth/me"),
    // Matches the desktop agent's fix in core/api_client.py -- without this
    // the model has no idea what "today"/"6 PM"/"in 20 minutes" means when
    // a reminder request comes through the extension.
    chat: (message) => request("POST", "/api/v1/assistant/chat", { json: { message, client_local_time: localIsoWithOffset() } }),
    confirmPending: (pendingId) => request("POST", `/api/v1/assistant/confirm/${pendingId}`),
    listReminders: () => request("GET", "/api/v1/reminders"),
  };
})();

// Mirrors dashboard/lib/api.ts's request/token patterns, adapted for
// chrome.storage.local instead of localStorage (extension popups don't
// share localStorage with any page, and chrome.storage is the correct
// primitive for extension-scoped persistent state).

const NovaAPI = (() => {
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
    chat: (message) => request("POST", "/api/v1/assistant/chat", { json: { message } }),
    confirmPending: (pendingId) => request("POST", `/api/v1/assistant/confirm/${pendingId}`),
    listReminders: () => request("GET", "/api/v1/reminders"),
  };
})();

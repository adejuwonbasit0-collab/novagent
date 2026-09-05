const $ = (id) => document.getElementById(id);

const loginView = $("view-login");
const chatView = $("view-chat");
const loginForm = $("login-form");
const loginError = $("login-error");
const chatForm = $("chat-form");
const chatInput = $("chat-input");
const messagesEl = $("messages");
const stateRing = $("state-ring");
const confirmBox = $("confirm-box");
const confirmText = $("confirm-text");
const pageContextEl = $("page-context");
const pageTitleEl = $("page-title");

let pendingConfirmId = null;

function setState(state) {
  stateRing.dataset.state = state;
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function showChatView() {
  loginView.classList.add("hidden");
  chatView.classList.remove("hidden");
  await loadPageContext();
}

function showLoginView() {
  chatView.classList.add("hidden");
  loginView.classList.remove("hidden");
}

async function loadPageContext() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.title && tab?.url?.startsWith("http")) {
      pageTitleEl.textContent = tab.title;
      pageContextEl.classList.remove("hidden");
      pageContextEl.dataset.url = tab.url;
      pageContextEl.dataset.title = tab.title;
    } else {
      pageContextEl.classList.add("hidden");
    }
  } catch {
    pageContextEl.classList.add("hidden");
  }
}

async function sendChat(message) {
  addMessage("user", message);
  chatInput.value = "";
  setState("thinking");
  chatInput.disabled = true;
  $("chat-submit").disabled = true;

  try {
    const reply = await NovaAPI.chat(message);
    addMessage("assistant", reply.reply);

    const needsConfirm = reply.tool_calls.find((tc) => tc.result === "REQUIRES_CONFIRMATION");
    if (needsConfirm) {
      pendingConfirmId = needsConfirm.pending_id;
      confirmText.textContent = needsConfirm.message || `Run ${needsConfirm.tool_name}?`;
      confirmBox.classList.remove("hidden");
    }
  } catch (err) {
    addMessage("assistant", `⚠️ ${err.message}`);
  } finally {
    setState("idle");
    chatInput.disabled = false;
    $("chat-submit").disabled = false;
    chatInput.focus();
  }
}

// ---- Login ----

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  $("login-submit").disabled = true;
  $("login-submit").textContent = "Signing in…";

  try {
    await NovaAPI.login($("email").value, $("password").value);
    await showChatView();
  } catch (err) {
    loginError.textContent = err.message;
    loginError.classList.remove("hidden");
  } finally {
    $("login-submit").disabled = false;
    $("login-submit").textContent = "Sign in";
  }
});

// ---- Chat ----

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (text) sendChat(text);
});

$("logout-btn").addEventListener("click", async () => {
  await NovaAPI.logout();
  messagesEl.innerHTML = "";
  showLoginView();
});

const MAX_PAGE_TEXT_CHARS = 6000; // keeps the request small and bounds what leaves the browser

/**
 * Runs in the page's own context via chrome.scripting.executeScript —
 * never injected automatically, only on this button click, and only for
 * the currently active tab (activeTab permission, not a blanket
 * <all_urls> content script). This is what makes "summarize this page"
 * honest: real page text, not just the title/URL, but pulled on-demand
 * rather than continuously watched.
 */
function extractReadableText() {
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll("script, style, noscript, svg, nav, footer").forEach((el) => el.remove());
  return clone.innerText.replace(/\s+/g, " ").trim();
}

$("summarize-btn").addEventListener("click", async () => {
  const title = pageContextEl.dataset.title;
  const url = pageContextEl.dataset.url;

  $("summarize-btn").disabled = true;
  $("summarize-btn").textContent = "Reading page…";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const [{ result: pageText }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractReadableText,
    });

    const truncated = (pageText || "").slice(0, MAX_PAGE_TEXT_CHARS);
    const truncatedNote = pageText && pageText.length > MAX_PAGE_TEXT_CHARS ? " (truncated)" : "";

    await sendChat(
      `Summarize this page for me. Title: "${title}". URL: ${url}.\n\nPage content${truncatedNote}:\n"""${truncated}"""`
    );
  } catch (err) {
    addMessage("assistant", `⚠️ Couldn't read this page: ${err.message}`);
  } finally {
    $("summarize-btn").disabled = false;
    $("summarize-btn").textContent = "Summarize this page";
  }
});

// ---- Confirmation flow ----

$("confirm-yes").addEventListener("click", async () => {
  if (!pendingConfirmId) return;
  confirmBox.classList.add("hidden");
  setState("executing");
  try {
    const result = await NovaAPI.confirmPending(pendingConfirmId);
    addMessage("assistant", result.message || `${result.tool_name}: ${result.result}`);
  } catch (err) {
    addMessage("assistant", `⚠️ ${err.message}`);
  } finally {
    setState("idle");
    pendingConfirmId = null;
  }
});

$("confirm-no").addEventListener("click", () => {
  confirmBox.classList.add("hidden");
  addMessage("assistant", "Okay, I won't do that.");
  pendingConfirmId = null;
});

// ---- Init ----

(async function init() {
  if (await NovaAPI.isLoggedIn()) {
    try {
      await NovaAPI.me();
      await showChatView();
      return;
    } catch {
      // token invalid/expired past refresh — fall through to login
    }
  }
  showLoginView();
})();

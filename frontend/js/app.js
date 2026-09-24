// ABIET web UI entry point: authentication, app shell and routing.

import { get, hasToken, post, setToken } from "./api.js";
import { banner, brandMark, h, icon, modal, storage, toast } from "./dom.js";
import { emit, loadConnections, on, selectConnection, state } from "./state.js";
import { renderAuth } from "./views/auth.js";
import { renderAsk } from "./views/ask.js";
import { renderHistory } from "./views/history.js";
import { renderConnections, renderConnectionForm } from "./views/connections.js";
import { renderInsights } from "./views/insights.js";

const app = document.getElementById("app");
let cleanup = null;
let currentNav = null;
let main = null;
let navLinks = {};
let picker = null;
let openMenu = null;

// One listener for the whole app: close the account menu when clicking elsewhere.
document.addEventListener("click", (e) => {
  if (openMenu && !openMenu.contains(e.target)) openMenu.hidden = true;
});

const ROUTES = [
  { pattern: /^#\/ask$/, nav: "ask", view: (el) => renderAsk(el) },
  { pattern: /^#\/history$/, nav: "history", view: (el) => renderHistory(el, { saved: false }) },
  { pattern: /^#\/saved$/, nav: "saved", view: (el) => renderHistory(el, { saved: true }) },
  { pattern: /^#\/connections$/, nav: "connections", view: (el) => renderConnections(el) },
  { pattern: /^#\/connections\/new$/, nav: "connections", view: (el) => renderConnectionForm(el, null) },
  { pattern: /^#\/connections\/(\d+)$/, nav: "connections", view: (el, m) => renderConnectionForm(el, Number(m[1])) },
  { pattern: /^#\/insights$/, nav: "insights", view: (el) => renderInsights(el) },
];

// --- Theme ------------------------------------------------------------------------

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function currentTheme() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  storage.set("abiet.theme", next);
  emit("theme", next);
}

applyTheme(storage.get("abiet.theme"));

// --- Shell ------------------------------------------------------------------------

function renderPicker() {
  if (!picker) return;
  picker.replaceChildren(
    ...(state.connections.length
      ? state.connections.map((c) => h("option", { value: c.id, selected: c.id === state.connectionId, text: c.name }))
      : [h("option", { value: "", text: "No connections" })]),
  );
  picker.disabled = !state.connections.length;
}

function changePasswordDialog() {
  const current = h("input", { type: "password", name: "current", autocomplete: "current-password", required: true });
  const next = h("input", { type: "password", name: "next", autocomplete: "new-password", minlength: 8, required: true });
  modal({
    title: "Change password",
    confirmText: "Change password",
    body: h("div", { class: "stack" },
      h("label", { class: "field" }, "Current password", current),
      h("label", { class: "field" }, "New password", h("span", { class: "hint", text: "At least 8 characters" }), next)),
    onConfirm: async () => {
      await post("/auth/change-password", { current_password: current.value, new_password: next.value });
      toast("Password changed");
    },
  });
}

function userMenu() {
  const menu = h("div", { class: "menu", hidden: true, role: "menu" },
    h("div", { class: "menu-head" },
      h("div", { style: { fontWeight: 600 }, text: state.user.username }),
      h("div", { class: "muted small", text: state.user.email }),
      state.user.is_admin ? h("span", { class: "badge info", text: "Administrator" }) : null),
    h("button", { type: "button", role: "menuitem", text: "Change password", onclick: () => { menu.hidden = true; changePasswordDialog(); } }),
    h("button", { type: "button", role: "menuitem", text: "API documentation", onclick: () => window.open("/docs", "_blank", "noopener") }),
    h("button", { type: "button", role: "menuitem", text: "Sign out", onclick: logout }),
  );
  const button = h("button", {
    class: "btn ghost", type: "button", "aria-haspopup": "menu",
    onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; },
  }, h("span", { text: state.user.username }));
  openMenu = menu;
  return h("div", { class: "user-menu" }, button, menu);
}

function renderShell() {
  picker = h("select", { "aria-label": "Database connection", onchange: (e) => selectConnection(e.target.value) });
  const link = (key, label) => (navLinks[key] = h("a", { href: `#/${key}`, text: label }));
  const themeBtn = h("button", { class: "btn ghost icon", type: "button", title: "Toggle light/dark theme", "aria-label": "Toggle theme", onclick: () => { toggleTheme(); themeBtn.replaceChildren(icon(currentTheme() === "dark" ? "sun" : "moon")); } }, icon(currentTheme() === "dark" ? "sun" : "moon"));
  const topbar = h("header", { class: "topbar" },
    h("a", { class: "brand", href: "#/ask", "aria-label": "ABIET home" }, brandMark(), h("span", { text: "ABIET" })),
    h("div", { class: "conn-picker" }, icon("schema"), picker),
    h("nav", { class: "nav", "aria-label": "Main" },
      link("ask", "Ask"), link("history", "History"), link("saved", "Saved"), link("connections", "Connections"), link("insights", "Insights")),
    h("div", { class: "spacer" }),
    themeBtn,
    userMenu(),
  );
  main = h("main", { id: "main" });
  const notices = [];
  if (!state.info.ai_configured) {
    notices.push(
      h("div", { class: "app-banner" },
        banner("warning",
          h("strong", { text: "AI is not configured. " }),
          "Set OPENAI_API_KEY (or OPENAI_BASE_URL for a compatible server) and restart ABIET to ask questions in plain English. You can still run SQL directly.")),
    );
  }
  app.replaceChildren(topbar, ...notices, main);
  renderPicker();
}

function route() {
  if (!state.user || !main) return;
  const hash = location.hash || "#/ask";
  const match = ROUTES.map((r) => ({ r, m: hash.match(r.pattern) })).find((x) => x.m);
  if (!match) {
    location.hash = "#/ask";
    return;
  }
  currentNav = match.r.nav;
  for (const [key, el] of Object.entries(navLinks)) el.classList.toggle("current", key === match.r.nav);
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
  main.replaceChildren();
  cleanup = match.r.view(main, match.m);
}

// --- Session ----------------------------------------------------------------------

async function startSession(user) {
  state.user = user;
  try {
    await loadConnections();
  } catch (err) {
    toast(err.message, "error");
  }
  renderShell();
  route();
}

function logout() {
  setToken(null);
  state.user = null;
  state.connections = [];
  state.schemas.clear();
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
  currentNav = null;
  main = null;
  showAuth();
}

function showAuth() {
  renderAuth(app, state.info, (user) => {
    if (!location.hash || location.hash === "#/") location.hash = "#/ask";
    startSession(user);
  });
}

on("connections", renderPicker);
on("connection", () => {
  renderPicker();
  if (currentNav === "ask") route();  // the workspace is per-connection
});
window.addEventListener("hashchange", route);
window.addEventListener("abiet:logout", () => {
  if (state.user) {
    toast("Your session expired. Please sign in again.");
    logout();
  }
});

async function boot() {
  try {
    state.info = await get("/info");
  } catch (err) {
    app.replaceChildren(h("div", { class: "auth-wrap" }, banner("error", err.message)));
    return;
  }
  if (hasToken()) {
    try {
      const user = await get("/auth/me");
      await startSession(user);
      return;
    } catch {
      setToken(null);
    }
  }
  showAuth();
}

boot();

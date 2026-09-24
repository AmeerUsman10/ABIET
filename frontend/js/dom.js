// DOM helpers. All text is inserted with textContent / text nodes - never innerHTML.

const SVG_NS = "http://www.w3.org/2000/svg";

function setProps(el, props) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "value" && "value" in el) el.value = value;
    else if (key === "checked" || key === "selected" || key === "disabled") el[key] = Boolean(value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
}

function appendChildren(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false || child === true) continue;
    el.append(child instanceof Node ? child : String(child));
  }
}

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  setProps(el, props);
  appendChildren(el, children);
  return el;
}

export function s(tag, props, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  setProps(el, props);
  appendChildren(el, children);
  return el;
}

const ICONS = {
  send: "M3 11.5 20.5 4 13 21.5l-2.5-7.5L3 11.5Z",
  play: "M7 4.5v15l12-7.5-12-7.5Z",
  copy: "M8 8h11v12H8zM5 16H4V4h12v1",
  edit: "M4 20h4L19 9l-4-4L4 16v4ZM13.5 6.5l4 4",
  star: "m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1 5.9-.8L12 3.5Z",
  download: "M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19.5h14",
  up: "M7 11v9H4v-9h3Zm0 0 4-7.5c1.5 0 2.5 1 2.2 2.6L12.6 10H18a2 2 0 0 1 2 2.3l-1.2 6A2 2 0 0 1 16.8 20H7",
  down: "M17 13V4h3v9h-3Zm0 0-4 7.5c-1.5 0-2.5-1-2.2-2.6L11.4 14H6a2 2 0 0 1-2-2.3l1.2-6A2 2 0 0 1 7.2 4H17",
  reply: "M9 8 4 12.5 9 17M4.5 12.5H14a6 6 0 0 1 6 6V20",
  refresh: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4v4.5H15",
  trash: "M5 7h14M9.5 7V4.5h5V7M7 7l1 13h8l1-13",
  plug: "M9 3v5m6-5v5M6.5 8h11v3.5a5.5 5.5 0 0 1-11 0V8ZM12 17v4",
  chevron: "m9 5 7 7-7 7",
  warn: "M12 4 2.5 20h19L12 4Zm0 6v4.5m0 2.5v.5",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-10v6m0-9v.5",
  x: "M6 6l12 12M18 6 6 18",
  check: "m5 12.5 4.5 4.5L19 7.5",
  table: "M4 5h16v14H4zM4 10h16M4 15h16M10 5v14",
  chart: "M5 20V11m7 9V5m7 15v-6M3 20.5h18",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0-13v2m0 14v2m9-9h-2M5 12H3m15.4-6.4L17 7M7 17l-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z",
  schema: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  plus: "M12 5v14M5 12h14",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Zm6.5 11 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z",
};

export function icon(name, extraClass = "") {
  return s(
    "svg",
    { class: `ico ${extraClass}`.trim(), viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" },
    s("path", { d: ICONS[name] || ICONS.info }),
  );
}

export function brandMark() {
  return s(
    "svg",
    { class: "brand-mark", viewBox: "0 0 32 32", "aria-hidden": "true" },
    s("rect", { width: "32", height: "32", rx: "8", fill: "#256abf" }),
    s("path", { d: "M9 22V16M14 22V10M19 22V13M24 22V18", stroke: "#fff", "stroke-width": "2.6", "stroke-linecap": "round" }),
  );
}

export function banner(kind, ...content) {
  const ico = kind === "info" ? "info" : "warn";
  return h("div", { class: `banner ${kind}`, role: kind === "error" ? "alert" : "status" }, icon(ico), h("div", { class: "grow" }, ...content));
}

export function spinner(label = "Loading…") {
  return h("div", { class: "thinking" }, h("div", { class: "spinner", "aria-hidden": "true" }), h("span", { text: label }));
}

export function toast(message, kind = "info", ms = 4000) {
  const box = document.getElementById("toasts");
  const el = h("div", { class: `toast ${kind}`, role: kind === "error" ? "alert" : "status", text: message });
  box.append(el);
  setTimeout(() => el.remove(), ms);
}

export function modal({ title, body, confirmText = "OK", cancelText = "Cancel", danger = false, onConfirm }) {
  return new Promise((resolve) => {
    const error = h("p", { class: "form-error", hidden: true });
    const confirmBtn = h("button", { class: `btn ${danger ? "danger" : "primary"}`, type: "submit", text: confirmText });
    const close = (value) => {
      backdrop.remove();
      document.removeEventListener("keydown", onKey);
      resolve(value);
    };
    const form = h(
      "form",
      { class: "card modal", role: "dialog", "aria-modal": "true", "aria-label": title },
      h("div", { class: "modal-head" }, h("h3", { text: title })),
      h("div", { class: "card-body stack" }, body, error),
      h("div", { class: "modal-foot" },
        cancelText ? h("button", { class: "btn", type: "button", text: cancelText, onclick: () => close(null) }) : null,
        confirmBtn),
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!onConfirm) return close(true);
      confirmBtn.disabled = true;
      error.hidden = true;
      try {
        const result = await onConfirm(form);
        close(result === undefined ? true : result);
      } catch (err) {
        error.textContent = err.message || String(err);
        error.hidden = false;
        confirmBtn.disabled = false;
      }
    });
    const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(null); } }, form);
    const onKey = (e) => { if (e.key === "Escape") close(null); };
    document.addEventListener("keydown", onKey);
    document.body.append(backdrop);
    const first = form.querySelector("input, textarea, select");
    (first || confirmBtn).focus();
  });
}

export function confirmDialog(title, message, confirmText = "Confirm", danger = false) {
  return modal({ title, body: h("p", { text: message }), confirmText, danger });
}

const numberFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const compactFmt = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

export function formatNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "");
  return numberFmt.format(value);
}

export function formatCompact(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "");
  return Math.abs(value) < 10000 ? numberFmt.format(value) : compactFmt.format(value);
}

export function formatPercent(value) {
  return value == null ? "–" : `${Math.round(value * 1000) / 10}%`;
}

export function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1) return "<1 ms";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
}

export function parseServerDate(value) {
  if (!value) return null;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function relativeTime(value) {
  const date = parseServerDate(value);
  if (!date) return "";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const units = [["minute", 60], ["hour", 3600], ["day", 86400], ["week", 604800]];
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (let i = units.length - 1; i >= 0; i--) {
    const [unit, size] = units[i];
    if (seconds >= size) {
      if (unit === "week" && seconds > 5 * 604800) return date.toLocaleDateString();
      return rtf.format(-Math.round(seconds / size), unit);
    }
  }
  return rtf.format(-Math.round(seconds / 60), "minute");
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard");
  } catch {
    toast("Could not copy - select the text and copy it manually", "error");
  }
}

export const storage = {
  get(key, fallback = null) {
    try {
      const value = localStorage.getItem(key);
      return value == null ? fallback : value;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      if (value == null) localStorage.removeItem(key);
      else localStorage.setItem(key, String(value));
    } catch {
      /* storage unavailable (private mode) - non-essential */
    }
  },
};

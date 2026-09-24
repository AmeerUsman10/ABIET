// Query history and saved queries.

import { del, get, patch, qs } from "../api.js";
import { banner, confirmDialog, formatDuration, formatNumber, h, icon, modal, relativeTime, spinner, toast } from "../dom.js";
import { state } from "../state.js";
import { openRecord } from "./ask.js";

const PAGE = 50;
const STATUS_LABELS = {
  success: ["good", "Success"],
  error: ["bad", "Error"],
  blocked: ["warn", "Blocked"],
  needs_confirmation: ["warn", "Needs confirmation"],
  clarification: ["info", "Clarification"],
  generated: ["info", "Not run"],
};

export function renderHistory(root, { saved }) {
  const search = h("input", { type: "search", placeholder: saved ? "Search saved queries" : "Search questions and SQL", "aria-label": "Search" });
  const connFilter = h("select", { "aria-label": "Connection" },
    h("option", { value: "", text: "All connections" }),
    ...state.connections.map((c) => h("option", { value: c.id, text: c.name })));
  const statusFilter = h("select", { "aria-label": "Status", hidden: saved },
    h("option", { value: "", text: "Any status" }),
    ...Object.entries(STATUS_LABELS).map(([value, [, label]]) => h("option", { value, text: label })));
  const list = h("div", { class: "card list" });
  const more = h("button", { class: "btn", type: "button", hidden: true, text: "Load more", onclick: () => load(false) });
  const count = h("span", { class: "muted small" });
  let offset = 0;
  let timer = null;
  let token = 0;

  root.replaceChildren(
    h("div", { class: "page" },
      h("div", { class: "page-head" },
        h("div", { class: "grow" },
          h("h2", { text: saved ? "Saved queries" : "History" }),
          h("p", { text: saved ? "Queries you saved for reuse. Run them again at any time." : "Every question and query you have run, with the SQL that was used." })),
        count),
      h("div", { class: "filters" }, search, connFilter, statusFilter),
      list,
      h("div", { class: "row", style: { justifyContent: "center", marginTop: "14px" } }, more)));

  async function load(reset = true) {
    const mine = ++token;
    if (reset) {
      offset = 0;
      list.replaceChildren(spinner());
    }
    more.disabled = true;
    try {
      const data = await get(`/queries${qs({
        saved: saved ? "true" : undefined,
        search: search.value.trim(),
        connection_id: connFilter.value,
        status: saved ? undefined : statusFilter.value,
        limit: PAGE,
        offset,
      })}`);
      if (mine !== token) return;
      if (reset) list.replaceChildren();
      data.items.forEach((item) => list.append(saved ? savedItem(item) : historyItem(item)));
      offset += data.items.length;
      more.hidden = offset >= data.total;
      count.textContent = `${formatNumber(data.total)} ${data.total === 1 ? "query" : "queries"}`;
      if (!data.total) {
        list.replaceChildren(h("div", { class: "empty" },
          h("p", { class: "muted", text: saved
            ? "Nothing saved yet. Use the star on an answer to save it here."
            : search.value || connFilter.value || statusFilter.value ? "No queries match these filters." : "No queries yet. Ask a question to get started." }),
          h("a", { class: "btn", href: "#/ask", text: "Ask a question" })));
      }
    } catch (err) {
      list.replaceChildren(h("div", { class: "card-body" }, banner("error", err.message)));
    } finally {
      more.disabled = false;
    }
  }

  function badges(item) {
    const [kind, label] = STATUS_LABELS[item.status] || ["", item.status];
    return h("div", { class: "row wrap" },
      h("span", { class: `badge ${kind}`, text: label }),
      item.row_count != null && item.status === "success" ? h("span", { class: "badge", text: `${formatNumber(item.row_count)} rows` }) : null,
      item.duration_ms != null && item.status === "success" ? h("span", { class: "badge", text: formatDuration(item.duration_ms) }) : null,
      item.rating === 1 ? h("span", { class: "badge good", text: "👍" }) : null,
      item.rating === -1 ? h("span", { class: "badge bad", text: "👎" }) : null,
      item.corrected_sql ? h("span", { class: "badge info", text: "Corrected" }) : null,
      item.repaired ? h("span", { class: "badge info", text: "Auto-repaired" }) : null);
  }

  function open(item) {
    if (!item.connection_id) {
      toast("The connection for this query was deleted", "error");
      return;
    }
    openRecord(item);
  }

  function removeButton(item, row) {
    return h("button", { class: "btn ghost sm icon", type: "button", title: "Delete from history", "aria-label": "Delete",
      onclick: async (e) => {
        e.stopPropagation();
        if (!(await confirmDialog("Delete query", "Remove this query from your history? Examples learned from it are removed too.", "Delete", true))) return;
        try {
          await del(`/queries/${item.id}`);
          row.remove();
        } catch (err) {
          toast(err.message, "error");
        }
      } }, icon("trash"));
  }

  function historyItem(item) {
    const row = h("div", { class: "list-item clickable", tabindex: "0", role: "button" });
    row.append(
      h("div", { class: "grow" },
        h("div", { class: `title${item.question ? "" : " mono"}`, text: item.question || item.executed_sql || "(empty)" }),
        h("div", { class: "sub", text: [relativeTime(item.created_at), item.connection_name || "deleted connection", item.question && item.executed_sql ? item.executed_sql.replace(/\s+/g, " ") : ""].filter(Boolean).join(" · ") }),
        h("div", { style: { marginTop: "6px" } }, badges(item))),
      removeButton(item, row));
    row.addEventListener("click", () => open(item));
    row.addEventListener("keydown", (e) => { if (e.key === "Enter") open(item); });
    return row;
  }

  function savedItem(item) {
    const row = h("div", { class: "list-item" });
    const title = h("div", { class: "title", text: item.title || item.question || "Saved query" });
    row.append(
      h("div", { class: "grow" },
        title,
        h("div", { class: "sub", text: [item.connection_name || "deleted connection", item.question && item.title !== item.question ? item.question : "", `saved ${relativeTime(item.created_at)}`].filter(Boolean).join(" · ") }),
        h("div", { class: "sub mono", text: (item.executed_sql || item.generated_sql || "").replace(/\s+/g, " ") })),
      h("button", { class: "btn sm", type: "button", onclick: () => open(item) }, icon("play"), "Open"),
      h("button", { class: "btn ghost sm", type: "button", onclick: async () => {
        const input = h("input", { type: "text", value: item.title || item.question || "", maxlength: 200, required: true });
        const updated = await modal({
          title: "Rename saved query", confirmText: "Rename",
          body: h("label", { class: "field" }, "Title", input),
          onConfirm: () => patch(`/queries/${item.id}`, { title: input.value.trim() }),
        });
        if (updated) {
          item.title = updated.title;
          title.textContent = updated.title;
        }
      } }, icon("edit"), "Rename"),
      h("button", { class: "btn ghost sm", type: "button", onclick: async () => {
        try {
          await patch(`/queries/${item.id}`, { is_saved: false });
          row.remove();
          toast("Removed from saved");
        } catch (err) {
          toast(err.message, "error");
        }
      } }, icon("star"), "Unsave"));
    return row;
  }

  const debounced = () => {
    clearTimeout(timer);
    timer = setTimeout(() => load(true), 250);
  };
  search.addEventListener("input", debounced);
  connFilter.addEventListener("change", () => load(true));
  statusFilter.addEventListener("change", () => load(true));
  load(true);
  return () => clearTimeout(timer);
}

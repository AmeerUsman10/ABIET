// The Ask workspace: schema browser, conversation thread and composer.

import { download, get, patch, post, qs } from "../api.js";
import { detectChart, hideTooltip, modelFromResult, renderChart } from "../chart.js";
import { banner, copyText, formatDuration, formatNumber, h, icon, modal, spinner, toast } from "../dom.js";
import { currentConnection, loadConnections, loadSchema, selectConnection, state } from "../state.js";

const DEMO_EXAMPLES = [
  "What was our monthly revenue over the last 12 months?",
  "Top 10 customers by revenue",
  "Revenue by region and customer segment",
  "Which product categories have the highest return rate?",
  "How did each sales rep perform against their annual quota in 2025?",
  "Average order value by sales channel",
];

const STATUS_BADGES = {
  success: ["good", "Success"],
  error: ["bad", "Error"],
  blocked: ["warn", "Blocked"],
  needs_confirmation: ["warn", "Needs confirmation"],
  clarification: ["info", "Needs clarification"],
  generated: ["info", "Not run"],
};

// Conversation state survives tab switches.
const session = { connectionId: null, turns: [], parentId: null, mode: null, pendingOpen: null };

/** Open a history record in the Ask workspace. */
export function openRecord(record) {
  session.pendingOpen = record;
  if (record.connection_id && record.connection_id !== state.connectionId) selectConnection(record.connection_id);
  location.hash = "#/ask";
}

function resetSession(connectionId) {
  session.connectionId = connectionId;
  session.turns = [];
  session.parentId = null;
}

/** Render the workspace. The router re-renders it when the selected connection changes. */
export function renderAsk(root) {
  const conn = currentConnection();
  if (!conn) {
    root.replaceChildren(noConnections());
    return null;
  }
  if (session.connectionId !== conn.id) resetSession(conn.id);
  if (!session.mode) session.mode = state.info.ai_configured ? "ask" : "sql";

  const thread = h("div", { class: "thread", "aria-live": "polite" });
  const schemaPanel = h("aside", { class: "schema-panel", "aria-label": "Database schema" });
  const composer = buildComposer(conn, thread, schemaPanel);
  const workspace = h("div", { class: `workspace${state.info.ai_configured ? "" : " with-banner"}` },
    schemaPanel,
    h("section", { class: "main-col" }, thread, composer.el));
  root.replaceChildren(workspace);

  renderSchemaPanel(schemaPanel, conn, composer);
  renderThread(thread, conn, composer);

  if (session.pendingOpen && session.pendingOpen.connection_id === conn.id) {
    const record = session.pendingOpen;
    session.pendingOpen = null;
    const turn = { kind: record.question ? "ask" : "sql", question: record.question, sql: record.executed_sql || record.generated_sql, response: { query: record, result: null }, reopened: true };
    session.turns.push(turn);
    session.parentId = record.question ? record.id : session.parentId;
    thread.append(turnView(turn, conn, composer));
    composer.refreshFollowUp();
  }
  thread.scrollTop = thread.scrollHeight;
  composer.focus();

  return () => hideTooltip();
}

function noConnections() {
  const addDemo = h("button", {
    class: "btn primary", type: "button",
    onclick: async () => {
      addDemo.disabled = true;
      try {
        const demo = await post("/connections/demo");
        await loadConnections();
        selectConnection(demo.id);
        toast("Demo database added");
      } catch (err) {
        toast(err.message, "error");
        addDemo.disabled = false;
      }
    },
  }, icon("sparkle"), "Try the demo database");
  return h("div", { class: "page" },
    h("div", { class: "empty" },
      h("h2", { text: "Connect a database to get started" }),
      h("p", { class: "muted", text: "ABIET reads your database schema and turns plain-English questions into SQL. Connect SQL Server, PostgreSQL, Oracle, MySQL or SQLite, or explore a sample sales database first." }),
      h("div", { class: "row wrap", style: { justifyContent: "center" } },
        addDemo,
        h("a", { class: "btn", href: "#/connections/new" }, icon("plug"), "Connect a database"))));
}

// --- Schema browser -----------------------------------------------------------------

function renderSchemaPanel(panel, conn, composer) {
  const search = h("input", { type: "search", placeholder: "Filter tables and columns", "aria-label": "Filter schema" });
  const list = h("div", { class: "schema-list" }, spinner("Reading schema…"));
  const refresh = h("button", { class: "btn ghost sm icon", type: "button", title: "Refresh schema", "aria-label": "Refresh schema", onclick: () => load(true) }, icon("refresh"));
  panel.replaceChildren(
    h("div", { class: "schema-head" },
      h("div", { class: "row" },
        h("div", { class: "grow" },
          h("div", { style: { fontWeight: 650 }, class: "tname", text: conn.name }),
          h("div", { class: "muted small", text: `${conn.db_label}${conn.read_only ? " · read-only" : " · writes allowed"}` })),
        refresh,
        h("button", { class: "btn ghost sm icon only-mobile", type: "button", "aria-label": "Close schema", onclick: () => panel.classList.remove("mobile-open") }, icon("x"))),
      search),
    list);

  let schema = null;
  const draw = () => {
    if (!schema) return;
    const term = search.value.trim().toLowerCase();
    const tables = schema.tables.filter(
      (t) => !term || t.name.toLowerCase().includes(term) || t.columns.some((c) => c.name.toLowerCase().includes(term)),
    );
    if (!tables.length) {
      list.replaceChildren(h("p", { class: "muted small", style: { padding: "8px" }, text: schema.tables.length ? "No matches" : "No tables found. Check the connection's schema setting." }));
      return;
    }
    list.replaceChildren(
      ...tables.map((t) => {
        const fullName = t.schema ? `${t.schema}.${t.name}` : t.name;
        const fks = new Map();
        for (const fk of t.foreign_keys || []) fk.columns.forEach((c, i) => fks.set(c, `${fk.referred_table}.${fk.referred_columns[i]}`));
        const cols = h("ul", { class: "schema-cols", hidden: !term },
          t.columns.map((c) =>
            h("li", { title: [c.type, fks.has(c.name) ? `→ ${fks.get(c.name)}` : "", c.values ? `values: ${c.values.join(", ")}` : "", c.comment || ""].filter(Boolean).join("\n"), onclick: () => composer.insert(c.name) },
              c.primary_key ? h("span", { class: "key", text: "PK" }) : fks.has(c.name) ? h("span", { class: "key", text: "FK" }) : null,
              h("span", { text: c.name }),
              h("span", { class: "ctype", text: c.type })),
          ));
        const item = h("div", { class: `schema-table${term ? " open" : ""}` });
        item.append(
          h("button", { type: "button", "aria-expanded": String(Boolean(term)), onclick: (e) => {
            cols.hidden = !cols.hidden;
            item.classList.toggle("open", !cols.hidden);
            e.currentTarget.setAttribute("aria-expanded", String(!cols.hidden));
          }, ondblclick: () => composer.insert(fullName) },
          icon("chevron", "chev"),
          h("span", { class: "tname", text: fullName }),
          t.kind === "view" ? h("span", { class: "badge", text: "view" }) : null),
          cols);
        return item;
      }),
    );
  };
  const load = async (force = false) => {
    refresh.disabled = true;
    list.replaceChildren(spinner(force ? "Refreshing schema…" : "Reading schema…"));
    try {
      schema = await loadSchema(conn.id, force);
      draw();
      if (force) toast(`Schema refreshed: ${schema.tables.length} tables`);
    } catch (err) {
      list.replaceChildren(
        h("div", { style: { padding: "8px" } },
          banner("error", h("strong", { text: "Could not read the schema. " }), err.message, " ",
            h("a", { href: `#/connections/${conn.id}`, text: "Edit connection" }))));
    } finally {
      refresh.disabled = false;
    }
  };
  search.addEventListener("input", draw);
  load();
}

// --- Composer -----------------------------------------------------------------------

function buildComposer(conn, thread, schemaPanel) {
  const input = h("textarea", { rows: 1, "aria-label": "Question" });
  const sendBtn = h("button", { class: "btn primary", type: "submit", title: "Send" }, icon("send"), h("span", { text: "Ask" }));
  const suggestBox = h("div", { class: "suggest-box", hidden: true, role: "listbox" });
  const followChip = h("div", { class: "chip", hidden: true });
  const newConvBtn = h("button", { class: "btn ghost sm", type: "button", hidden: true, onclick: () => { session.parentId = null; session.turns = []; renderThread(thread, conn, api); refreshFollowUp(); input.focus(); } }, icon("plus"), "New conversation");
  const askMode = h("button", { type: "button", text: "Ask", onclick: () => setMode("ask") });
  const sqlMode = h("button", { type: "button", text: "SQL", onclick: () => setMode("sql") });
  const schemaBtn = h("button", { class: "btn ghost sm only-mobile", type: "button", onclick: () => schemaPanel.classList.add("mobile-open") }, icon("schema"), "Schema");

  let suggestions = [];
  let highlighted = -1;
  let suggestTimer = null;
  let suggestRequest = 0;
  let busy = false;

  function setMode(mode) {
    if (mode === "ask" && !state.info.ai_configured) {
      toast("AI is not configured on this server. Use SQL mode or set OPENAI_API_KEY.", "error");
      mode = "sql";
    }
    session.mode = mode;
    askMode.classList.toggle("current", mode === "ask");
    sqlMode.classList.toggle("current", mode === "sql");
    input.classList.toggle("sql", mode === "sql");
    input.placeholder = mode === "ask"
      ? (session.parentId ? "Ask a follow-up question…" : `Ask a question about ${conn.name}…`)
      : "Write a SQL query (Ctrl+Enter to run)…";
    input.setAttribute("aria-label", mode === "ask" ? "Question" : "SQL query");
    sendBtn.lastChild.textContent = mode === "ask" ? "Ask" : "Run";
    sendBtn.replaceChild(icon(mode === "ask" ? "send" : "play"), sendBtn.firstChild);
    hideSuggestions();
    refreshFollowUp();
  }

  function refreshFollowUp() {
    const parent = session.turns.findLast((t) => t.response?.query?.id === session.parentId);
    followChip.hidden = !(session.mode === "ask" && parent && parent.question);
    if (!followChip.hidden) {
      followChip.replaceChildren(
        icon("reply"),
        h("span", { text: `Follow-up to: ${parent.question}` }),
        h("button", { type: "button", "aria-label": "Ask a standalone question instead", title: "Ask a standalone question", text: "×", onclick: () => { session.parentId = null; refreshFollowUp(); input.focus(); } }));
    }
    newConvBtn.hidden = !session.turns.length;
    if (session.mode === "ask") input.placeholder = session.parentId ? "Ask a follow-up question…" : `Ask a question about ${conn.name}…`;
  }

  function autosize() {
    input.style.height = "auto";
    input.style.height = `${Math.min(220, input.scrollHeight + 2)}px`;
  }

  function hideSuggestions() {
    suggestBox.hidden = true;
    suggestions = [];
    highlighted = -1;
  }

  function showSuggestions(items) {
    suggestions = items.filter((q) => q.trim().toLowerCase() !== input.value.trim().toLowerCase()).slice(0, 6);
    highlighted = -1;
    if (!suggestions.length) return hideSuggestions();
    suggestBox.replaceChildren(
      ...suggestions.map((q, i) =>
        h("button", { type: "button", role: "option", text: q, onmousedown: (e) => { e.preventDefault(); pick(i); } })),
    );
    suggestBox.hidden = false;
  }

  function pick(i) {
    input.value = suggestions[i];
    hideSuggestions();
    autosize();
    input.focus();
  }

  input.addEventListener("input", () => {
    autosize();
    if (session.mode !== "ask") return;
    clearTimeout(suggestTimer);
    const text = input.value.trim();
    if (text.length < 2) return hideSuggestions();
    const request = ++suggestRequest;
    suggestTimer = setTimeout(async () => {
      try {
        const items = await get(`/query/suggestions${qs({ connection_id: conn.id, q: text, limit: 6 })}`);
        // Ignore answers that arrive after the question was sent or edited further.
        if (request === suggestRequest && document.activeElement === input && input.value.trim() === text) showSuggestions(items);
      } catch {
        hideSuggestions();
      }
    }, 200);
  });
  input.addEventListener("blur", () => setTimeout(hideSuggestions, 100));
  input.addEventListener("keydown", (e) => {
    if (!suggestBox.hidden && suggestions.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        highlighted = (highlighted + (e.key === "ArrowDown" ? 1 : -1) + suggestions.length) % suggestions.length;
        [...suggestBox.children].forEach((el, i) => el.classList.toggle("hl", i === highlighted));
        return;
      }
      if (e.key === "Enter" && highlighted >= 0) {
        e.preventDefault();
        pick(highlighted);
        return;
      }
      if (e.key === "Escape") return hideSuggestions();
    }
    const submitKey = session.mode === "ask" ? e.key === "Enter" && !e.shiftKey : e.key === "Enter" && (e.ctrlKey || e.metaKey);
    if (submitKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  const form = h("form", { class: "composer" }, suggestBox, input, sendBtn);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    sendBtn.disabled = true;
    clearTimeout(suggestTimer);
    suggestRequest++;
    hideSuggestions();
    input.value = "";
    autosize();
    try {
      await submitTurn(session.mode, text, conn, thread, api);
    } finally {
      busy = false;
      sendBtn.disabled = false;
      refreshFollowUp();
      input.focus();
    }
  });

  const el = h("div", { class: "composer-wrap" },
    h("div", { class: "composer-meta" },
      h("div", { class: "seg", role: "group", "aria-label": "Input mode" }, askMode, sqlMode),
      followChip, h("div", { class: "spacer" }), schemaBtn, newConvBtn),
    form);

  const api = {
    el,
    refreshFollowUp,
    focus: () => input.focus(),
    setText(text, mode) {
      if (mode) setMode(mode);
      input.value = text;
      autosize();
      input.focus();
    },
    insert(text) {
      schemaPanel.classList.remove("mobile-open");
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? input.value.length;
      const before = input.value.slice(0, start);
      const pad = before && !/\s$/.test(before) ? " " : "";
      input.value = before + pad + text + input.value.slice(end);
      const pos = before.length + pad.length + text.length;
      input.setSelectionRange(pos, pos);
      autosize();
      input.focus();
    },
  };
  setMode(session.mode);
  return api;
}

// --- Thread -------------------------------------------------------------------------

function renderThread(thread, conn, composer) {
  if (!session.turns.length) {
    thread.replaceChildren(emptyThread(conn, composer));
    return;
  }
  thread.replaceChildren(...session.turns.map((turn) => turnView(turn, conn, composer)));
}

function emptyThread(conn, composer) {
  const examples = h("div", { class: "examples" });
  const box = h("div", { class: "empty" },
    h("h2", { text: `Ask ${conn.name} anything` }),
    h("p", { class: "muted", text: state.info.ai_configured
      ? "Questions are translated into SQL for this database, checked for safety, run, and explained. Rate the answers so ABIET learns your data."
      : "AI is not configured, so write SQL directly in SQL mode. Queries are checked for safety before they run." }),
    examples);
  const addExamples = (items, mode = "ask") => {
    for (const q of items) {
      examples.append(h("button", { class: "example-btn", type: "button", text: q, onclick: () => composer.setText(q, mode) }));
    }
  };
  if (!state.info.ai_configured) {
    loadSchema(conn.id).then((schema) => {
      const t = schema.tables[0];
      if (t) addExamples([`SELECT * FROM ${t.schema ? `${t.schema}.` : ""}${t.name}`], "sql");
    }).catch(() => {});
  } else if (conn.is_demo) {
    addExamples(DEMO_EXAMPLES);
  } else {
    get(`/query/suggestions${qs({ connection_id: conn.id, limit: 6 })}`)
      .then((items) => {
        if (items.length) addExamples(items);
        else {
          return loadSchema(conn.id).then((schema) => {
            const names = schema.tables.filter((t) => t.kind === "table").slice(0, 3).map((t) => t.name);
            addExamples(names.flatMap((n, i) => (i === 0 ? [`How many rows are in ${n}?`, `Show 10 rows from ${n}`] : [`Summarize ${n}`])));
          });
        }
      })
      .catch(() => {});
  }
  return box;
}

async function submitTurn(mode, text, conn, thread, composer) {
  if (!session.turns.length) thread.replaceChildren();
  const turn = mode === "ask" ? { kind: "ask", question: text } : { kind: "sql", sql: text };
  turn.pending = true;
  session.turns.push(turn);
  const el = turnView(turn, conn, composer);
  thread.append(el);
  thread.scrollTop = thread.scrollHeight;
  try {
    turn.response = mode === "ask"
      ? await post("/query/ask", { connection_id: conn.id, question: text, parent_id: session.parentId })
      : await post("/query/run", { connection_id: conn.id, sql: text });
    if (mode === "ask") session.parentId = turn.response.query.id;
  } catch (err) {
    turn.error = err.message;
  }
  turn.pending = false;
  replaceTurn(turn, conn, composer);
  (turn.el || el).scrollIntoView({ block: "start", behavior: "smooth" });
}

function replaceTurn(turn, conn, composer) {
  const old = turn.el;
  const next = turnView(turn, conn, composer);
  if (old && old.parentNode) old.replaceWith(next);
}

function turnView(turn, conn, composer) {
  const el = h("article", { class: "turn" });
  turn.el = el;
  el.append(turn.kind === "ask"
    ? h("div", { class: "q-bubble", text: turn.question })
    : h("div", { class: "q-bubble sql", text: turn.sql }));

  if (turn.pending) {
    el.append(h("div", { class: "answer" }, spinner(turn.kind === "ask" ? "Reading the schema and writing SQL…" : "Running query…")));
    return el;
  }
  if (turn.error) {
    el.append(h("div", { class: "answer" }, h("div", { class: "answer-head" }, h("div", { class: "grow" }, banner("error", turn.error)))));
    return el;
  }
  el.append(answerView(turn, conn, composer));
  return el;
}

// --- Answer card ----------------------------------------------------------------------

function answerView(turn, conn, composer) {
  const r = turn.response;
  const q = r.query;
  const card = h("div", { class: "answer" });
  const rerender = () => replaceTurn(turn, conn, composer);

  const [badgeKind, badgeText] = STATUS_BADGES[q.status] || ["", q.status];
  const edited = Boolean(q.question && q.generated_sql && q.executed_sql && q.executed_sql !== q.generated_sql && !q.repaired);
  const meta = h("div", { class: "answer-meta" },
    h("span", { class: `badge ${badgeKind}` }, h("span", { class: "dot" }), badgeText),
    r.result && r.result.affected_rows == null ? h("span", { class: "badge", text: `${formatNumber(r.result.row_count)} row${r.result.row_count === 1 ? "" : "s"}` }) : null,
    r.result && r.result.affected_rows != null ? h("span", { class: "badge", text: `${formatNumber(r.result.affected_rows)} row(s) affected` }) : null,
    q.duration_ms != null && q.status === "success" ? h("span", { class: "badge", text: formatDuration(q.duration_ms) }) : null,
    q.repaired ? h("span", { class: "badge info", title: "The first query failed; ABIET fixed it using the database error", text: "Auto-repaired" }) : null,
    edited ? h("span", { class: "badge info", title: "You edited the SQL the AI wrote", text: "Edited" }) : null,
    r.result?.truncated ? h("span", { class: "badge warn", text: `First ${formatNumber(r.result.row_count)} rows shown` }) : null,
    q.rating === 1 ? h("span", { class: "badge good", text: "Marked correct" }) : null,
    q.corrected_sql ? h("span", { class: "badge info", text: "Corrected" }) : null,
  );

  const headText = edited
    ? "You edited the SQL. If this result answers the question, mark it correct so ABIET learns from it."
    : r.clarification || q.explanation || (turn.kind === "sql" || !q.question ? "SQL query" : "");
  card.append(h("div", { class: "answer-head" },
    h("div", { class: "explain" }, headText ? h("p", { text: headText }) : null, meta)));

  if (q.status === "clarification") {
    card.append(banner("info", "Reply below to clarify. Your answer will be treated as a follow-up to this question."));
  } else if (q.status === "error" && q.error) {
    card.append(banner("error", h("strong", { text: "The query failed. " }), q.error));
  } else if (q.status === "blocked" && q.error) {
    card.append(banner("warning", h("strong", { text: "Not run. " }), q.error));
  } else if (q.status === "needs_confirmation") {
    const runBtn = h("button", { class: "btn sm danger", type: "button", text: "Run this statement",
      onclick: async () => {
        runBtn.disabled = true;
        try {
          turn.response = await post("/query/run", { connection_id: conn.id, sql: q.executed_sql || q.generated_sql, query_id: q.id, confirm_write: true });
          rerender();
        } catch (err) {
          toast(err.message, "error");
          runBtn.disabled = false;
        }
      } });
    card.append(banner("warning", h("strong", { text: "This statement changes data. " }), "Review the SQL carefully before running it. ", runBtn));
  }

  const sql = q.executed_sql || q.generated_sql;
  if (sql) card.append(sqlBlock(turn, conn, sql, rerender));

  if (r.result && r.result.columns.length) {
    card.append(...resultView(turn, r, conn, rerender));
  } else if (turn.reopened && sql && q.status !== "needs_confirmation") {
    const runAgain = h("button", { class: "btn sm", type: "button", onclick: async () => {
      runAgain.disabled = true;
      try {
        turn.response = await post("/query/run", { connection_id: conn.id, sql, query_id: q.id });
        turn.reopened = false;
        rerender();
      } catch (err) {
        toast(err.message, "error");
        runAgain.disabled = false;
      }
    } }, icon("play"), "Run again");
    card.append(h("div", { class: "result-bar" }, runAgain, h("div", { class: "spacer" }), ...actionButtons(turn, conn, rerender)));
  } else if (q.question && q.status !== "clarification") {
    card.append(h("div", { class: "result-bar" }, h("div", { class: "spacer" }), ...actionButtons(turn, conn, rerender)));
  }
  return card;
}

function sqlBlock(turn, conn, sql, rerender) {
  const q = turn.response.query;
  const pre = h("pre", { text: sql });
  const block = h("div", { class: "sql-block" });
  const bar = h("div", { class: "sql-bar" },
    h("span", { text: q.corrected_sql && q.corrected_sql !== sql ? "SQL (you provided a correction)" : "SQL" }),
    h("div", { class: "spacer" }),
    h("button", { class: "btn ghost sm", type: "button", onclick: () => copyText(sql) }, icon("copy"), "Copy"),
    h("button", { class: "btn ghost sm", type: "button", onclick: () => edit() }, icon("edit"), "Edit"));
  block.append(bar, pre);

  function edit() {
    const area = h("textarea", { "aria-label": "Edit SQL", spellcheck: "false", value: sql, rows: Math.min(16, sql.split("\n").length + 2) });
    const runBtn = h("button", { class: "btn primary sm", type: "submit" }, icon("play"), "Run");
    const form = h("form", {},
      area,
      h("div", { class: "sql-edit-actions" },
        runBtn,
        h("button", { class: "btn sm", type: "button", text: "Cancel", onclick: () => block.replaceChildren(bar, pre) }),
        h("span", { class: "muted small", text: "Ctrl+Enter to run. If the edited query is right, mark it 👍 so ABIET learns it." })));
    area.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        form.requestSubmit();
      }
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      runBtn.disabled = true;
      try {
        turn.response = await post("/query/run", { connection_id: conn.id, sql: area.value, query_id: q.id });
        turn.reopened = false;
        rerender();
      } catch (err) {
        toast(err.message, "error");
        runBtn.disabled = false;
      }
    });
    block.replaceChildren(form);
    area.focus();
  }
  return block;
}

function actionButtons(turn, conn, rerender) {
  const q = turn.response.query;
  const buttons = [];
  const saveBtn = h("button", { class: `btn ghost sm${q.is_saved ? " active" : ""}`, type: "button", title: q.is_saved ? "Remove from saved" : "Save query", "aria-pressed": String(q.is_saved),
    onclick: async () => {
      try {
        turn.response.query = await patch(`/queries/${q.id}`, { is_saved: !q.is_saved });
        toast(turn.response.query.is_saved ? "Saved. Find it under Saved." : "Removed from saved");
        rerender();
      } catch (err) {
        toast(err.message, "error");
      }
    } }, icon("star"), q.is_saved ? "Saved" : "Save");
  buttons.push(saveBtn);
  if (turn.response.result && turn.response.result.columns.length) {
    buttons.push(h("button", { class: "btn ghost sm", type: "button", title: "Download all rows as CSV",
      onclick: async () => {
        try {
          await download(`/queries/${q.id}/export.csv`, `query-${q.id}.csv`);
        } catch (err) {
          toast(err.message, "error");
        }
      } }, icon("download"), "CSV"));
  }
  if (q.question) {
    buttons.push(
      h("button", { class: `btn ghost sm icon${q.rating === 1 ? " active" : ""}`, type: "button", title: "Correct answer", "aria-label": "Mark answer correct", "aria-pressed": String(q.rating === 1),
        onclick: () => sendFeedback(turn, q.rating === 1 ? { rating: 0 } : { rating: 1 }, rerender) }, icon("up")),
      h("button", { class: `btn ghost sm icon${q.rating === -1 ? " active" : ""}`, type: "button", title: "Wrong answer", "aria-label": "Mark answer wrong", "aria-pressed": String(q.rating === -1),
        onclick: () => (q.rating === -1 ? sendFeedback(turn, { rating: 0 }, rerender) : negativeFeedback(turn, rerender)) }, icon("down")),
    );
  }
  return buttons;
}

async function sendFeedback(turn, body, rerender) {
  try {
    turn.response.query = await post(`/queries/${turn.response.query.id}/feedback`, body);
    if (body.rating === 1) toast("Thanks! ABIET will reuse this answer for similar questions.");
    rerender();
  } catch (err) {
    toast(err.message, "error");
  }
}

function negativeFeedback(turn, rerender) {
  const q = turn.response.query;
  const original = q.executed_sql || q.generated_sql || "";
  const comment = h("textarea", { rows: 3, placeholder: "e.g. Revenue should exclude cancelled orders" });
  const corrected = h("textarea", { rows: 8, class: "mono", spellcheck: "false", value: q.corrected_sql || original });
  modal({
    title: "What was wrong?",
    confirmText: "Send feedback",
    body: h("div", { class: "stack" },
      h("label", { class: "field" }, "Comment", h("span", { class: "hint", text: "Optional" }), comment),
      h("label", { class: "field" }, "Correct SQL", h("span", { class: "hint", text: "Optional. If you fix the query, ABIET uses your version as an example for similar questions." }), corrected)),
    onConfirm: async () => {
      const fixed = corrected.value.trim();
      const body = { rating: -1, comment: comment.value.trim() || null };
      if (fixed && fixed !== original.trim()) body.corrected_sql = fixed;
      turn.response.query = await post(`/queries/${q.id}/feedback`, body);
      toast(body.corrected_sql ? "Thanks! Your correction will guide similar questions." : "Thanks for the feedback.");
      rerender();
    },
  });
}

// --- Results --------------------------------------------------------------------------

function resultView(turn, r, conn, rerender) {
  const spec = detectChart(r.result.columns, r.result.rows, r.chart);
  turn.view ||= spec && r.chart ? "chart" : "table";
  if (!spec) turn.view = "table";
  const body = h("div", { class: "result-body" });
  const tableBtn = h("button", { type: "button", onclick: () => show("table") }, "Table");
  const chartBtn = h("button", { type: "button", onclick: () => show("chart") }, "Chart");
  let stopChart = null;

  function show(view) {
    turn.view = view;
    tableBtn.classList.toggle("current", view === "table");
    chartBtn.classList.toggle("current", view === "chart");
    stopChart?.();
    stopChart = null;
    if (view === "chart" && spec) {
      const typeSelect = h("select", { "aria-label": "Chart type" },
        h("option", { value: "bar", selected: spec.type === "bar", text: "Bar" }),
        h("option", { value: "line", selected: spec.type === "line", text: "Line" }));
      const holder = h("div");
      typeSelect.addEventListener("change", () => {
        spec.type = typeSelect.value;
        stopChart?.();
        stopChart = renderChart(holder, modelFromResult(r.result.columns, r.result.rows, spec));
      });
      body.replaceChildren(
        h("div", { class: "chart-controls" }, h("span", { text: `${spec.y.map((i) => r.result.columns[i]).join(", ")} by ${r.result.columns[spec.x]}` }), h("div", { class: "spacer" }), typeSelect),
        holder);
      stopChart = renderChart(holder, modelFromResult(r.result.columns, r.result.rows, spec));
    } else {
      body.replaceChildren(dataTable(r.result));
    }
  }

  const bar = h("div", { class: "result-bar" },
    spec ? h("div", { class: "seg", role: "group", "aria-label": "Result view" }, tableBtn, chartBtn) : null,
    h("div", { class: "spacer" }),
    ...actionButtons(turn, conn, rerender));
  show(turn.view);
  return [bar, body];
}

function dataTable(result) {
  const { columns } = result;
  let rows = result.rows.map((row, i) => ({ row, i }));
  let sortCol = -1;
  let sortDir = 1;
  const numeric = columns.map((_, c) => result.rows.some((r) => typeof r[c] === "number"));
  const tbody = h("tbody");
  const headCells = columns.map((name, c) =>
    h("th", { scope: "col", title: "Sort", class: numeric[c] ? "num" : null, onclick: () => sortBy(c) }, h("span", { text: name }), h("span", { class: "sort" })));

  function cell(value, c) {
    if (value == null) return h("td", { class: "null", text: "NULL" });
    if (typeof value === "object") return h("td", { class: "mono", title: JSON.stringify(value), text: JSON.stringify(value) });
    if (typeof value === "number") return h("td", { class: "num", text: formatNumber(value) });
    const text = String(value);
    return h("td", { title: text.length > 60 ? text : null, class: numeric[c] ? "num" : null, text });
  }

  function draw() {
    tbody.replaceChildren(
      ...rows.map(({ row, i }) => h("tr", {}, h("td", { class: "rownum", text: String(i + 1) }), ...row.map((v, c) => cell(v, c)))),
    );
    headCells.forEach((th, c) => { th.lastChild.textContent = c === sortCol ? (sortDir > 0 ? "▲" : "▼") : ""; });
  }

  function sortBy(c) {
    sortDir = c === sortCol ? -sortDir : 1;
    sortCol = c;
    rows = [...rows].sort((a, b) => {
      const x = a.row[c];
      const y = b.row[c];
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "number" && typeof y === "number") return (x - y) * sortDir;
      return String(x).localeCompare(String(y), undefined, { numeric: true }) * sortDir;
    });
    draw();
  }

  draw();
  if (!result.rows.length) return h("p", { class: "muted", style: { padding: "12px 16px" }, text: "The query returned no rows." });
  return h("div", { class: "table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {}, h("th", { class: "rownum", scope: "col", text: "#" }), ...headCells)),
      tbody));
}

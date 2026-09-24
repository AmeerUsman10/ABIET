// Database connections: list, add/edit form, tests, learned examples.

import { del, get, post, put } from "../api.js";
import { banner, confirmDialog, formatDuration, h, icon, relativeTime, spinner, toast } from "../dom.js";
import { forgetSchema, loadConnections, loadTypes, selectConnection, state } from "../state.js";

const ABBREV = { mssql: "MS", postgresql: "PG", oracle: "OR", mysql: "MY", sqlite: "SQ" };

function testResult(result) {
  return result.ok
    ? banner("info", h("strong", { text: "Connected. " }), `${result.server_version ? `Server version ${result.server_version}. ` : ""}Responded in ${formatDuration(result.latency_ms)}.`)
    : banner("error", h("strong", { text: "Connection failed. " }), result.message);
}

export function renderConnections(root) {
  const grid = h("div", { class: "conn-grid" });
  const addDemo = h("button", { class: "btn", type: "button", onclick: async () => {
    addDemo.disabled = true;
    try {
      const demo = await post("/connections/demo");
      await loadConnections();
      selectConnection(demo.id);
      toast("Demo database added");
      draw();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      addDemo.disabled = false;
    }
  } }, icon("sparkle"), "Add demo database");

  root.replaceChildren(
    h("div", { class: "page" },
      h("div", { class: "page-head" },
        h("div", { class: "grow" },
          h("h2", { text: "Connections" }),
          h("p", { text: "Databases ABIET can query. Passwords are encrypted at rest. For safety, connect with a database user that only has read access." })),
        addDemo,
        h("a", { class: "btn primary", href: "#/connections/new" }, icon("plus"), "Add connection")),
      grid));

  function card(conn) {
    const status = h("div");
    const examples = h("div", { class: "examples-list", hidden: true });
    const testBtn = h("button", { class: "btn ghost sm", type: "button", onclick: async () => {
      testBtn.disabled = true;
      status.replaceChildren(spinner("Testing…"));
      try {
        status.replaceChildren(testResult(await post(`/connections/${conn.id}/test`)));
      } catch (err) {
        status.replaceChildren(banner("error", err.message));
      } finally {
        testBtn.disabled = false;
      }
    } }, icon("plug"), "Test");
    const learnedBtn = h("button", { class: "btn ghost sm", type: "button", onclick: async () => {
      if (!examples.hidden) {
        examples.hidden = true;
        return;
      }
      examples.hidden = false;
      examples.replaceChildren(spinner());
      try {
        const items = await get(`/learning/examples?connection_id=${conn.id}`);
        examples.replaceChildren(
          items.length
            ? h("p", { class: "muted small", text: `${items.length} approved or corrected ${items.length === 1 ? "query is" : "queries are"} reused as examples for similar questions:` })
            : h("p", { class: "muted small", text: "Nothing learned yet. Mark correct answers with 👍 or correct wrong ones with 👎, and ABIET will reuse them for similar questions." }),
          ...items.map((ex) =>
            h("div", {},
              h("div", { class: "row" }, h("strong", { class: "grow", text: ex.question }), h("span", { class: `badge ${ex.source === "corrected" ? "info" : "good"}`, text: ex.source })),
              h("pre", { class: "mono", text: ex.sql }))),
        );
      } catch (err) {
        examples.replaceChildren(banner("error", err.message));
      }
    } }, icon("sparkle"), "Learned");
    const where = conn.db_type === "sqlite"
      ? conn.database
      : [conn.host, conn.options?.instance ? `\\${conn.options.instance}` : "", conn.port ? `:${conn.port}` : ""].join("");
    return h("div", { class: "card conn-card" },
      h("div", { class: "card-body" },
        h("div", { class: "row" },
          h("div", { class: "db-icon", text: ABBREV[conn.db_type] || "DB" }),
          h("div", { class: "grow" },
            h("h3", { text: conn.name }),
            h("div", { class: "muted small", text: conn.db_label }))),
        h("dl", { class: "kv" },
          h("dt", { text: conn.db_type === "sqlite" ? "File" : "Server" }), h("dd", { text: where || "–" }),
          conn.db_type !== "sqlite" ? [h("dt", { text: conn.db_type === "oracle" ? "Service" : "Database" }), h("dd", { text: conn.database || "(default)" })] : null,
          conn.db_type !== "sqlite" ? [h("dt", { text: "User" }), h("dd", { text: conn.options?.trusted_connection ? "Windows authentication" : conn.username || "–" })] : null,
          h("dt", { text: "Schema" }), h("dd", { text: conn.table_count != null ? `${conn.table_count} tables · read ${relativeTime(conn.schema_cached_at)}` : "not read yet" })),
        h("div", { class: "row wrap" },
          conn.read_only ? h("span", { class: "badge good", text: "Read-only" }) : h("span", { class: "badge warn", text: "Writes allowed" }),
          conn.is_demo ? h("span", { class: "badge info", text: "Demo" }) : null,
          conn.id === state.connectionId ? h("span", { class: "badge info", text: "Selected" }) : null),
        status),
      examples,
      h("div", { class: "conn-foot" },
        h("button", { class: "btn sm primary", type: "button", onclick: () => { selectConnection(conn.id); location.hash = "#/ask"; } }, "Ask"),
        testBtn,
        learnedBtn,
        h("a", { class: "btn ghost sm", href: `#/connections/${conn.id}` }, icon("edit"), "Edit"),
        h("div", { class: "spacer" }),
        h("button", { class: "btn ghost sm icon danger", type: "button", title: "Delete connection", "aria-label": "Delete connection", onclick: async () => {
          const ok = await confirmDialog("Delete connection", `Delete "${conn.name}"? Its query history stays but can no longer be re-run.`, "Delete", true);
          if (!ok) return;
          try {
            await del(`/connections/${conn.id}`);
            forgetSchema(conn.id);
            await loadConnections();
            draw();
            toast("Connection deleted");
          } catch (err) {
            toast(err.message, "error");
          }
        } }, icon("trash"))));
  }

  function draw() {
    if (!state.connections.length) {
      grid.replaceChildren(
        h("div", { class: "card", style: { gridColumn: "1 / -1" } },
          h("div", { class: "empty" },
            h("h3", { text: "No connections yet" }),
            h("p", { class: "muted", text: "Add your own database, or add the demo sales database to try ABIET." }))));
      return;
    }
    grid.replaceChildren(...state.connections.map(card));
  }

  loadConnections().then(draw).catch((err) => grid.replaceChildren(banner("error", err.message)));
  draw();
}

export function renderConnectionForm(root, connectionId) {
  root.replaceChildren(h("div", { class: "page" }, spinner()));
  Promise.all([loadTypes(), connectionId ? get(`/connections/${connectionId}`) : null])
    .then(([types, existing]) => buildForm(root, types, existing))
    .catch((err) => root.replaceChildren(h("div", { class: "page" }, banner("error", err.message))));
}

function buildForm(root, types, existing) {
  const byKey = Object.fromEntries(types.map((t) => [t.key, t]));
  const editing = Boolean(existing);
  const demo = existing?.is_demo;
  const f = {
    name: h("input", { type: "text", required: true, maxlength: 100, value: existing?.name || "" }),
    db_type: h("select", { disabled: demo }, ...types.map((t) => h("option", { value: t.key, text: t.label, selected: (existing?.db_type || "mssql") === t.key }))),
    host: h("input", { type: "text", value: existing?.host || "", placeholder: "localhost", autocomplete: "off" }),
    port: h("input", { type: "number", min: 1, max: 65535, value: existing?.port ?? "" }),
    database: h("input", { type: "text", value: existing?.database || "", autocomplete: "off" }),
    username: h("input", { type: "text", value: existing?.username || "", autocomplete: "off" }),
    password: h("input", { type: "password", autocomplete: "new-password", placeholder: existing?.has_password ? "Unchanged - type to replace" : "" }),
    read_only: h("input", { type: "checkbox", checked: existing ? existing.read_only : true, disabled: demo }),
  };
  const clearPassword = h("input", { type: "checkbox" });
  const optionsBox = h("div", { class: "form-grid full" });
  const optionInputs = {};
  const testArea = h("div");
  const error = h("p", { class: "form-error", role: "alert", hidden: true });
  const dbLabel = h("span");
  const dbHint = h("span", { class: "hint" });
  const serverFields = [];
  const typeHint = h("div");
  const writeWarning = banner("warning", "Writes are allowed: ABIET can run INSERT, UPDATE and DELETE statements on this database after you confirm each one. Keep connections read-only unless you need this.");

  const field = (label, input, hint, cls = "") => {
    const el = h("label", { class: `field ${cls}`.trim() }, label, hint ? h("span", { class: "hint", text: hint }) : null, input);
    return el;
  };
  const hostField = field("Host", f.host);
  const portField = field("Port", f.port);
  const userField = field("Username", f.username);
  const passField = h("label", { class: "field" }, "Password", f.password,
    editing && existing.has_password ? h("span", { class: "check small", style: { marginTop: "4px" } }, clearPassword, h("span", { text: "Remove stored password" })) : null);
  serverFields.push(hostField, portField, userField, passField);

  function renderOptions() {
    const type = byKey[f.db_type.value];
    const current = existing && existing.db_type === type.key ? existing.options || {} : {};
    for (const key of Object.keys(optionInputs)) delete optionInputs[key];
    optionsBox.replaceChildren(
      ...type.options.map((opt) => {
        if (opt.type === "bool") {
          const input = h("input", { type: "checkbox", checked: current[opt.key] ?? opt.default ?? false, disabled: demo });
          optionInputs[opt.key] = input;
          return h("label", { class: "check" }, input, h("span", {}, h("span", { text: opt.label }), opt.help ? h("span", { class: "muted small", text: ` - ${opt.help}` }) : null));
        }
        const input = h("input", { type: "text", value: current[opt.key] || "", disabled: demo });
        optionInputs[opt.key] = input;
        return field(opt.label, input, opt.help);
      }),
    );
    const trusted = optionInputs.trusted_connection;
    if (trusted) {
      const sync = () => { userField.hidden = passField.hidden = trusted.checked; };
      trusted.addEventListener("change", sync);
      sync();
    }
  }

  function syncType() {
    const type = byKey[f.db_type.value];
    const sqlite = type.key === "sqlite";
    serverFields.forEach((el) => { el.hidden = sqlite; });
    f.port.placeholder = type.default_port ? String(type.default_port) : "";
    dbLabel.textContent = sqlite ? "File name" : type.key === "oracle" ? "Service name" : "Database";
    dbHint.textContent = sqlite
      ? "A .sqlite/.db file inside the server's data/databases folder"
      : type.key === "oracle" ? "e.g. XEPDB1 or ORCLPDB1" : type.key === "mssql" ? "Leave empty for the login's default database" : "";
    typeHint.replaceChildren(
      type.key === "mssql"
        ? banner("info", "SQL Server Express on your own machine: use host ", h("code", { text: "localhost" }), " (or ", h("code", { text: "host.docker.internal" }), " when ABIET runs in Docker) with instance ", h("code", { text: "SQLEXPRESS" }), ", or leave the instance empty and use the fixed TCP port. SQL authentication must be enabled for username/password logins.")
        : "",
    );
    renderOptions();
  }

  function collect() {
    const type = f.db_type.value;
    const options = {};
    for (const [key, input] of Object.entries(optionInputs)) options[key] = input.type === "checkbox" ? input.checked : input.value.trim();
    const body = {
      db_type: type,
      host: f.host.value.trim() || null,
      port: f.port.value ? Number(f.port.value) : null,
      database: f.database.value.trim() || null,
      username: f.username.value.trim() || null,
      options,
      read_only: f.read_only.checked,
    };
    if (type === "sqlite") Object.assign(body, { host: null, port: null, username: null });
    return body;
  }

  const testBtn = h("button", { class: "btn", type: "button", onclick: async () => {
    testBtn.disabled = true;
    testArea.replaceChildren(spinner("Testing connection…"));
    try {
      const body = { ...collect(), password: f.password.value || null };
      if (editing && !f.password.value && !clearPassword.checked) body.connection_id = existing.id;
      testArea.replaceChildren(testResult(await post("/connections/test", body)));
    } catch (err) {
      testArea.replaceChildren(banner("error", err.message));
    } finally {
      testBtn.disabled = false;
    }
  } }, icon("plug"), "Test connection");
  const saveBtn = h("button", { class: "btn primary", type: "submit", text: editing ? "Save changes" : "Save connection" });

  const form = h("form", { class: "card" },
    h("div", { class: "card-body stack" },
      h("div", { class: "form-grid" },
        field("Name", f.name, "Shown in the connection picker"),
        field("Database type", f.db_type),
        h("div", { class: "full" }, typeHint),
        hostField, portField,
        h("label", { class: "field full" }, dbLabel, dbHint, f.database),
        userField, passField,
        optionsBox,
        h("label", { class: "check full" }, f.read_only, h("span", {}, h("strong", { text: "Read-only" }), h("span", { class: "muted", text: " - only SELECT queries can run (recommended)" }))),
        h("div", { class: "full" }, writeWarning)),
      testArea,
      error,
      h("div", { class: "row wrap" }, saveBtn, testBtn, h("a", { class: "btn ghost", href: "#/connections", text: "Cancel" }))));

  f.db_type.addEventListener("change", () => {
    syncType();
    if (!editing && !f.port.value) f.port.value = "";
  });
  const syncWrite = () => { writeWarning.hidden = f.read_only.checked; };
  f.read_only.addEventListener("change", syncWrite);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    saveBtn.disabled = true;
    error.hidden = true;
    try {
      const body = { ...collect(), name: f.name.value.trim() };
      let saved;
      if (editing) {
        if (demo) {
          saved = await put(`/connections/${existing.id}`, { name: body.name });
        } else {
          if (f.password.value) body.password = f.password.value;
          if (clearPassword.checked) body.clear_password = true;
          saved = await put(`/connections/${existing.id}`, body);
        }
        forgetSchema(existing.id);
      } else {
        body.password = f.password.value || null;
        saved = await post("/connections", body);
      }
      await loadConnections();
      selectConnection(saved.id);
      toast(editing ? "Connection updated" : "Connection saved");
      location.hash = "#/connections";
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      saveBtn.disabled = false;
    }
  });

  root.replaceChildren(
    h("div", { class: "page", style: { maxWidth: "760px" } },
      h("div", { class: "page-head" },
        h("div", { class: "grow" },
          h("h2", { text: editing ? `Edit ${existing.name}` : "Add a connection" }),
          h("p", { text: demo ? "The demo database is read-only; only its name can be changed." : "Connection details are stored on the ABIET server; the password is encrypted." }))),
      form));
  syncType();
  syncWrite();
  f.name.focus();
}

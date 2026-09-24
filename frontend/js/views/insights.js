// Insights: accuracy, usage and learning analytics.

import { get, post, qs } from "../api.js";
import { renderChart } from "../chart.js";
import { banner, formatDuration, formatNumber, formatPercent, h, icon, spinner, toast } from "../dom.js";
import { state } from "../state.js";
import { openRecord } from "./ask.js";

const FEATURE_LABELS = {
  filter: "Filters (WHERE)",
  aggregate: "Aggregations",
  join: "Joins",
  sort: "Sorting",
  cte: "CTEs (WITH)",
  subquery: "Subqueries",
  window: "Window functions",
};

export function renderInsights(root) {
  let scope = "me";
  let days = 30;
  const content = h("div");
  const stops = [];
  const scopeSeg = h("div", { class: "seg", role: "group", "aria-label": "Scope", hidden: !state.user.is_admin });
  const scopes = [["me", "My queries"], ["all", "Everyone"]].map(([value, label]) =>
    h("button", { type: "button", text: label, onclick: () => { scope = value; sync(); load(); } }));
  scopeSeg.append(...scopes);
  const period = h("select", { "aria-label": "Period" },
    ...[[7, "Last 7 days"], [30, "Last 30 days"], [90, "Last 90 days"], [365, "Last 12 months"]].map(([value, label]) =>
      h("option", { value, text: label, selected: value === days })));
  period.addEventListener("change", () => { days = Number(period.value); load(); });
  const sync = () => scopes.forEach((b, i) => b.classList.toggle("current", ["me", "all"][i] === scope));

  root.replaceChildren(
    h("div", { class: "page" },
      h("div", { class: "page-head" },
        h("div", { class: "grow" },
          h("h2", { text: "Insights" }),
          h("p", { text: "How accurately ABIET answers, where it struggles, and what it has learned from feedback." })),
        scopeSeg, period),
      content));

  function clearCharts() {
    while (stops.length) stops.pop()();
  }

  async function load() {
    content.style.opacity = content.childElementCount ? "0.55" : "1";
    if (!content.childElementCount) content.replaceChildren(spinner());
    try {
      const data = await get(`/learning/insights${qs({ scope, days })}`);
      clearCharts();
      draw(data);
    } catch (err) {
      content.replaceChildren(banner("error", err.message));
    } finally {
      content.style.opacity = "1";
    }
  }

  function kpi(label, value, sub) {
    return h("div", { class: "card kpi" },
      h("div", { class: "label", text: label }),
      h("div", { class: "value", text: value }),
      sub ? h("div", { class: "sub", text: sub }) : null);
  }

  function section(title, ...body) {
    return h("div", { class: "card" }, h("div", { class: "card-body stack" }, h("h3", { text: title }), ...body));
  }

  function draw({ analysis, suggestions }) {
    const t = analysis.totals;
    const fb = analysis.feedback;
    const activity = h("div");
    const features = h("div");
    const aiBox = h("div");
    const aiBtn = h("button", { class: "btn", type: "button", disabled: !state.info.ai_configured, title: state.info.ai_configured ? "" : "AI is not configured",
      onclick: async () => {
        aiBtn.disabled = true;
        aiBox.replaceChildren(spinner("Analyzing…"));
        try {
          const ai = await post(`/learning/insights/ai${qs({ scope, days })}`);
          aiBox.replaceChildren(
            h("p", { text: ai.summary }),
            ai.recommendations.length ? h("ul", { class: "suggestions" }, ai.recommendations.map((r) => h("li", { text: r }))) : null);
        } catch (err) {
          aiBox.replaceChildren(banner("error", err.message));
        } finally {
          aiBtn.disabled = false;
        }
      } }, icon("sparkle"), "Analyze with AI");

    const hasActivity = analysis.daily.some((d) => d.total);
    const featureEntries = Object.entries(analysis.query_features);

    content.replaceChildren(
      h("div", { class: "kpis" },
        kpi("Queries", formatNumber(t.queries), `${formatNumber(t.ai_questions)} asked in plain English`),
        kpi("Success rate", formatPercent(t.success_rate), `${formatNumber(t.success)} succeeded, ${formatNumber(t.errors)} failed`),
        kpi("Approval rate", formatPercent(fb.approval_rate), `${formatNumber(fb.positive)} 👍 · ${formatNumber(fb.negative)} 👎`),
        kpi("Learned examples", formatNumber(fb.corrections + fb.positive), `${formatNumber(fb.corrections)} corrections`),
        kpi("Auto-repaired", formatNumber(t.repaired), "queries fixed after a database error"),
        kpi("Avg. run time", t.avg_duration_ms == null ? "–" : formatDuration(t.avg_duration_ms), `${formatNumber(t.blocked)} blocked by safety checks`)),
      h("div", { class: "insight-grid" },
        h("div", { class: "full" }, section(`Activity, last ${analysis.period_days} days`,
          hasActivity ? activity : h("p", { class: "muted", text: "No queries in this period." }))),
        section("Suggestions", h("ul", { class: "suggestions" }, suggestions.map((s) => h("li", { text: s })))),
        section("Most common errors",
          analysis.top_errors.length
            ? h("div", { class: "list" }, analysis.top_errors.map((e) =>
              h("div", { class: "list-item", style: { padding: "8px 0" } },
                h("div", { class: "grow mono small", text: e.error }),
                h("span", { class: "badge bad", text: `${e.count}×` }))))
            : h("p", { class: "muted", text: "No failed queries recorded." })),
        section("What queries use",
          featureEntries.length ? features : h("p", { class: "muted", text: "Run some queries to see which SQL features they use." })),
        section("Recent 👎 answers",
          analysis.recent_negative.length
            ? h("div", { class: "list" }, analysis.recent_negative.map((n) =>
              h("div", { class: "list-item clickable", style: { padding: "8px 0" }, tabindex: "0", role: "button",
                onclick: () => get(`/queries/${n.id}`).then(openRecord).catch((err) => toast(err.message, "error")) },
              h("div", { class: "grow" },
                h("div", { class: "title", text: n.question }),
                n.comment ? h("div", { class: "sub", text: n.comment }) : null))))
            : h("p", { class: "muted", text: "No negative feedback in your history." })),
        h("div", { class: "full" }, section("AI analysis",
          h("p", { class: "muted", text: "Have the language model review these statistics and recommend improvements." }),
          aiBox, h("div", {}, aiBtn)))));

    if (hasActivity) {
      stops.push(renderChart(activity, {
        kind: "column",
        stacked: true,
        labels: analysis.daily.map((d) => d.date.slice(5)),
        series: [
          { name: "Succeeded", cls: "st-good", values: analysis.daily.map((d) => d.success) },
          { name: "Failed", cls: "st-critical", values: analysis.daily.map((d) => d.error) },
          { name: "Other (blocked, clarification)", cls: "s7", values: analysis.daily.map((d) => d.total - d.success - d.error) },
        ],
      }));
    }
    if (featureEntries.length) {
      stops.push(renderChart(features, {
        kind: "hbar",
        labels: featureEntries.map(([k]) => FEATURE_LABELS[k] || k),
        series: [{ name: "Queries", cls: "s1", values: featureEntries.map(([, v]) => v) }],
      }));
    }
  }

  sync();
  load();
  return clearCharts;
}

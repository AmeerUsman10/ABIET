// Dependency-free SVG charts: horizontal bars, columns (grouped or stacked) and lines.
// Marks follow a fixed spec: bars <= 24px with a 4px rounded data-end (square at the
// baseline), 2px lines, >= 8px end dots with a surface ring, hairline gridlines,
// a single value axis, a legend for 2+ series, and hover/focus tooltips.

import { formatCompact, formatNumber, h, s } from "./dom.js";

const MAX_SERIES = 6;
const MAX_BARS = 40;
const MAX_POINTS = 400;
const TIME_NAME = /(date|time|day|week|month|year|quarter|period)/i;
const TIME_VALUE = /^(\d{4}(-\d{1,2}(-\d{1,2})?)?([T ][\d:.]+.*)?|\d{4}-?Q[1-4]|Q[1-4][ -]?\d{4})$/;
const ID_NAME = /(^|_)id$/i;

// --- Choosing a chart -----------------------------------------------------------

function numericColumns(columns, rows) {
  return columns.map(
    (_, i) => rows.some((r) => typeof r[i] === "number") && rows.every((r) => r[i] == null || typeof r[i] === "number"),
  );
}

/** Decide whether and how to chart a result. Returns null when a chart would not help. */
export function detectChart(columns, rows, hint) {
  if (!rows || rows.length < 2 || !columns || columns.length < 2) return null;
  const numeric = numericColumns(columns, rows);
  const index = (name) => columns.indexOf(name);
  let x = -1;
  let y = [];
  if (hint && hint.x != null && index(hint.x) >= 0) {
    x = index(hint.x);
    y = (hint.y || []).map(index).filter((i) => i >= 0 && i !== x && numeric[i]);
  }
  if (x < 0 || !y.length) {
    x = columns.findIndex((_, i) => !numeric[i]);
    if (x < 0) x = columns.findIndex((c) => TIME_NAME.test(c));
    y = columns.map((_, i) => i).filter((i) => i !== x && numeric[i] && !ID_NAME.test(columns[i]));
  }
  if (x < 0 || !y.length) return null;
  const values = rows.map((r) => r[x]);
  const timeLike = TIME_NAME.test(columns[x]) || values.every((v) => v != null && TIME_VALUE.test(String(v)));
  let type = timeLike ? "line" : "bar";
  if (hint && (hint.type === "bar" || hint.type === "pie")) type = "bar";
  if (hint && hint.type === "line") type = "line";
  if (type === "line" && rows.length < 3) type = "bar";
  return { type, x, y: y.slice(0, MAX_SERIES), timeLike, share: Boolean(hint && hint.type === "pie" && y.length === 1) };
}

export function modelFromResult(columns, rows, spec) {
  const limit = spec.type === "line" ? MAX_POINTS : MAX_BARS;
  const used = rows.slice(0, limit);
  return {
    labels: used.map((r) => (r[spec.x] == null ? "(empty)" : String(r[spec.x]))),
    series: spec.y.map((i, n) => ({ name: columns[i], cls: `s${n + 1}`, values: used.map((r) => r[i]) })),
    kind: spec.type === "line" ? "line" : spec.timeLike ? "column" : "hbar",
    share: spec.share,
    clipped: rows.length > limit ? limit : 0,
  };
}

// --- Shared helpers --------------------------------------------------------------

let measureCtx;
function textWidth(text, size = 12) {
  measureCtx ||= document.createElement("canvas").getContext("2d");
  measureCtx.font = `${size}px system-ui, -apple-system, "Segoe UI", sans-serif`;
  return measureCtx.measureText(text).width;
}

function fitText(text, maxWidth, size = 12) {
  if (textWidth(text, size) <= maxWidth) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (textWidth(`${text.slice(0, mid)}…`, size) <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return lo > 0 ? `${text.slice(0, lo)}…` : "…";
}

function niceScale(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { lo: 0, hi: 1, ticks: [0, 1] };
  if (min === max) {
    if (min === 0) max = 1;
    else if (min > 0) min = 0;
    else max = 0;
  }
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const err = raw / mag;
  const step = (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1) * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { lo, hi, ticks };
}

function extent(model, stacked) {
  let min = 0;
  let max = 0;
  if (stacked) {
    model.labels.forEach((_, i) => {
      let pos = 0;
      let neg = 0;
      for (const series of model.series) {
        const v = series.values[i];
        if (typeof v === "number") (v >= 0 ? (pos += v) : (neg += v));
      }
      max = Math.max(max, pos);
      min = Math.min(min, neg);
    });
  } else {
    for (const series of model.series) {
      for (const v of series.values) {
        if (typeof v === "number") {
          max = Math.max(max, v);
          min = Math.min(min, v);
        }
      }
    }
  }
  return [min, max];
}

/** Bar path with a rounded data-end and a square base. Horizontal when `horizontal`. */
function barPath(x0, x1, y, thickness, horizontal, roundEnd = true) {
  const len = Math.abs(x1 - x0);
  const r = roundEnd ? Math.min(4, len, thickness / 2) : 0;
  const dir = x1 >= x0 ? 1 : -1;
  if (horizontal) {
    const e = x1;
    return `M${x0},${y}H${e - dir * r}Q${e},${y} ${e},${y + r}V${y + thickness - r}Q${e},${y + thickness} ${e - dir * r},${y + thickness}H${x0}Z`;
  }
  // vertical: x0/x1 are baseline/end on the y axis, y is the left edge
  const e = x1;
  const d = x1 <= x0 ? -1 : 1; // -1 = grows upward
  return `M${y},${x0}V${e - d * r}Q${y},${e} ${y + r},${e}H${y + thickness - r}Q${y + thickness},${e} ${y + thickness},${e - d * r}V${x0}Z`;
}

function tooltipEl() {
  return document.getElementById("tooltip");
}

function showTooltip(title, rows, clientX, clientY, lineKeys) {
  const tip = tooltipEl();
  if (!tip) return;
  tip.replaceChildren(
    h("div", { class: "tt-title", text: title }),
    ...rows.map((r) =>
      h("div", { class: "tt-row" },
        h("span", { class: `lk sw ${r.cls}${lineKeys ? " lk" : ""}` }),
        h("span", { class: "v", text: r.value }),
        h("span", { class: "n", text: r.name })),
    ),
  );
  tip.hidden = false;
  const { innerWidth, innerHeight } = window;
  const rect = tip.getBoundingClientRect();
  let left = clientX + 14;
  let top = clientY + 14;
  if (left + rect.width > innerWidth - 8) left = clientX - rect.width - 14;
  if (top + rect.height > innerHeight - 8) top = clientY - rect.height - 14;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${Math.max(8, top)}px`;
}

export function hideTooltip() {
  const tip = tooltipEl();
  if (tip) tip.hidden = true;
}

function seriesRows(model, i) {
  const total = model.share ? model.series[0].values.reduce((a, v) => a + (typeof v === "number" ? v : 0), 0) : 0;
  return model.series.map((series) => {
    const v = series.values[i];
    let value = v == null ? "–" : formatNumber(v);
    if (model.share && total && typeof v === "number") value += ` (${((v / total) * 100).toFixed(1)}%)`;
    return { name: series.name, cls: series.cls, value };
  });
}

function legend(model, lineKeys) {
  if (model.series.length < 2) return null;
  return h("div", { class: "legend" },
    model.series.map((series) =>
      h("span", { class: "key" }, h("span", { class: `sw ${series.cls}${lineKeys ? " lk" : ""}` }), h("span", { text: series.name })),
    ),
  );
}

function focusPoint(el) {
  const rect = el.getBoundingClientRect();
  return [rect.left + rect.width / 2, rect.top];
}

// --- Horizontal bars (categories) -------------------------------------------------

function drawHBars(model, width) {
  const n = model.series.length;
  const thick = n === 1 ? 20 : Math.max(8, Math.min(16, Math.floor(36 / n)));
  const band = n * thick + (n - 1) * 2 + 12;
  const labelW = Math.min(width * 0.36, Math.max(...model.labels.map((l) => textWidth(l))) + 16);
  const [min, max] = extent(model, false);
  const scale = niceScale(min, max, Math.max(2, Math.floor(width / 110)));
  const total = model.share ? model.series[0].values.reduce((a, v) => a + (typeof v === "number" ? v : 0), 0) : 0;
  const tipText = (v) => (model.share && total ? `${((v / total) * 100).toFixed(1)}%` : formatCompact(v));
  const showTips = n === 1 && model.labels.length <= 25;
  const valueW = showTips ? Math.max(...model.series[0].values.map((v) => (typeof v === "number" ? textWidth(tipText(v), 11.5) : 0))) + 10 : 8;
  const left = labelW;
  const right = width - valueW;
  const top = 4;
  const height = top + model.labels.length * band + 22;
  const xs = (v) => left + ((v - scale.lo) / (scale.hi - scale.lo)) * (right - left);
  const zero = xs(0);

  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": "Bar chart" });
  for (const t of scale.ticks) {
    const x = Math.round(xs(t)) + 0.5;
    svg.append(s("line", { class: t === 0 ? "base-line" : "grid-line", x1: x, x2: x, y1: top, y2: height - 20 }));
    svg.append(s("text", { class: "tick", x, y: height - 6, "text-anchor": "middle" }, formatCompact(t)));
  }
  model.labels.forEach((label, i) => {
    const y0 = top + i * band + 6;
    svg.append(s("text", { class: "cat-label", x: labelW - 8, y: y0 + (band - 12) / 2 + 4, "text-anchor": "end" }, fitText(label, labelW - 12)));
    const marks = [];
    model.series.forEach((series, k) => {
      const v = series.values[i];
      if (typeof v !== "number") return;
      const y = y0 + k * (thick + 2);
      const mark = s("path", { class: `mark rect ${series.cls}`, d: barPath(zero, xs(v), y, thick, true) });
      marks.push(mark);
      svg.append(mark);
      if (showTips) {
        const end = xs(v);
        svg.append(s("text", { class: "value-label", x: v >= 0 ? end + 5 : end - 5, y: y + thick / 2 + 4, "text-anchor": v >= 0 ? "start" : "end" }, tipText(v)));
      }
    });
    const hit = s("rect", { class: "hit", x: 0, y: y0 - 6, width, height: band, tabindex: "0", "aria-label": `${label}: ${seriesRows(model, i).map((r) => `${r.name} ${r.value}`).join(", ")}` });
    const on = (x, y) => { marks.forEach((m) => m.classList.add("hl")); showTooltip(label, seriesRows(model, i), x, y, false); };
    const off = () => { marks.forEach((m) => m.classList.remove("hl")); hideTooltip(); };
    hit.addEventListener("pointermove", (e) => on(e.clientX, e.clientY));
    hit.addEventListener("pointerleave", off);
    hit.addEventListener("focus", () => on(...focusPoint(hit)));
    hit.addEventListener("blur", off);
    svg.append(hit);
  });
  return svg;
}

// --- Columns (time or ordered categories), grouped or stacked ------------------------

function axisLabelsEvery(labels, plotW) {
  const widest = Math.max(...labels.map((l) => textWidth(l, 11))) + 12;
  return Math.max(1, Math.ceil((labels.length * widest) / plotW));
}

function drawColumns(model, width, stacked = false) {
  const height = 260;
  const [min, max] = extent(model, stacked);
  const scale = niceScale(min, max, 5);
  const left = Math.max(...scale.ticks.map((t) => textWidth(formatCompact(t), 11))) + 10;
  const right = width - 4;
  const top = 8;
  const bottom = height - 24;
  const ys = (v) => bottom - ((v - scale.lo) / (scale.hi - scale.lo)) * (bottom - top);
  const zero = ys(0);
  const count = model.labels.length;
  const bandW = (right - left) / count;
  const n = stacked ? 1 : model.series.length;
  const thick = Math.max(1, Math.min(24, (bandW - 4 - (n - 1) * 2) / n));
  const groupW = n * thick + (n - 1) * 2;
  const every = axisLabelsEvery(model.labels, right - left);

  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": "Column chart" });
  for (const t of scale.ticks) {
    const y = Math.round(ys(t)) + 0.5;
    svg.append(s("line", { class: t === 0 ? "base-line" : "grid-line", x1: left, x2: right, y1: y, y2: y }));
    svg.append(s("text", { class: "tick", x: left - 6, y: y + 4, "text-anchor": "end" }, formatCompact(t)));
  }
  model.labels.forEach((label, i) => {
    const bx = left + i * bandW + (bandW - groupW) / 2;
    const marks = [];
    if (stacked) {
      let pos = 0;
      const segments = model.series
        .map((series) => ({ series, v: series.values[i] }))
        .filter((seg) => typeof seg.v === "number" && seg.v > 0);
      segments.forEach((seg, k) => {
        const isTop = k === segments.length - 1;
        const y0 = ys(pos) - (k > 0 ? 1 : 0);
        const y1 = ys(pos + seg.v) + (isTop ? 0 : 1);
        pos += seg.v;
        if (y0 - y1 < 0.5) return;
        const mark = s("path", { class: `mark rect ${seg.series.cls}`, d: barPath(y0, y1, bx, thick, false, isTop) });
        marks.push(mark);
        svg.append(mark);
      });
    } else {
      model.series.forEach((series, k) => {
        const v = series.values[i];
        if (typeof v !== "number") return;
        const mark = s("path", { class: `mark rect ${series.cls}`, d: barPath(zero, ys(v), bx + k * (thick + 2), thick, false) });
        marks.push(mark);
        svg.append(mark);
      });
    }
    if (i % every === 0) {
      svg.append(s("text", { class: "tick", x: left + i * bandW + bandW / 2, y: height - 6, "text-anchor": "middle" }, fitText(label, bandW * every - 6, 11)));
    }
    const hit = s("rect", { class: "hit", x: left + i * bandW, y: top, width: bandW, height: bottom - top, tabindex: "0", "aria-label": `${label}: ${seriesRows(model, i).map((r) => `${r.name} ${r.value}`).join(", ")}` });
    const on = (x, y) => { marks.forEach((m) => m.classList.add("hl")); showTooltip(label, seriesRows(model, i), x, y, false); };
    const off = () => { marks.forEach((m) => m.classList.remove("hl")); hideTooltip(); };
    hit.addEventListener("pointermove", (e) => on(e.clientX, e.clientY));
    hit.addEventListener("pointerleave", off);
    hit.addEventListener("focus", () => on(...focusPoint(hit)));
    hit.addEventListener("blur", off);
    svg.append(hit);
  });
  return svg;
}

// --- Lines ----------------------------------------------------------------------

function drawLines(model, width) {
  const height = 260;
  const [min, max] = extent(model, false);
  const scale = niceScale(min, max, 5);
  const single = model.series.length === 1;
  const lastValue = (series) => [...series.values].reverse().find((v) => typeof v === "number");
  const endW = single ? textWidth(formatCompact(lastValue(model.series[0]) ?? 0), 12) + 14 : 10;
  const tickW = Math.max(...scale.ticks.map((t) => textWidth(formatCompact(t), 11))) + 10;
  const left = Math.max(tickW, textWidth(model.labels[0] || "", 11) / 2 + 2); // room to centre the first x label
  const right = width - endW;
  const top = 10;
  const bottom = height - 24;
  const count = model.labels.length;
  const step = count > 1 ? (right - left) / (count - 1) : 0;
  const xs = (i) => left + i * step;
  const ys = (v) => bottom - ((v - scale.lo) / (scale.hi - scale.lo)) * (bottom - top);
  const every = axisLabelsEvery(model.labels, right - left);

  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": "Line chart" });
  for (const t of scale.ticks) {
    const y = Math.round(ys(t)) + 0.5;
    svg.append(s("line", { class: t === 0 ? "base-line" : "grid-line", x1: left, x2: right, y1: y, y2: y }));
    svg.append(s("text", { class: "tick", x: left - 6, y: y + 4, "text-anchor": "end" }, formatCompact(t)));
  }
  model.labels.forEach((label, i) => {
    if (i % every === 0) {
      svg.append(s("text", { class: "tick", x: xs(i), y: height - 6, "text-anchor": "middle" }, fitText(label, step * every - 6 || 80, 11)));
    }
  });
  for (const series of model.series) {
    let d = "";
    let pen = false;
    series.values.forEach((v, i) => {
      if (typeof v !== "number") { pen = false; return; }
      d += `${pen ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`;
      pen = true;
    });
    if (single) {
      const pts = series.values.map((v, i) => [i, v]).filter(([, v]) => typeof v === "number");
      if (pts.length > 1) {
        const area = `M${xs(pts[0][0])},${ys(Math.max(scale.lo, 0))}` + pts.map(([i, v]) => `L${xs(i)},${ys(v)}`).join("") + `L${xs(pts.at(-1)[0])},${ys(Math.max(scale.lo, 0))}Z`;
        svg.append(s("path", { class: `area ${series.cls}`, d: area }));
      }
    }
    svg.append(s("path", { class: `line ${series.cls}`, d }));
    const lastIndex = series.values.findLastIndex((v) => typeof v === "number");
    if (lastIndex >= 0) {
      const v = series.values[lastIndex];
      svg.append(s("circle", { class: `dot ${series.cls}`, cx: xs(lastIndex), cy: ys(v), r: 4 }));
      if (single) svg.append(s("text", { class: "end-label", x: xs(lastIndex) + 8, y: ys(v) + 4 }, formatCompact(v)));
    }
  }

  const cross = s("line", { class: "crosshair", y1: top, y2: bottom, visibility: "hidden" });
  const hoverDots = model.series.map((series) => s("circle", { class: `dot ${series.cls}`, r: 4, visibility: "hidden" }));
  svg.append(cross, ...hoverDots);
  const overlay = s("rect", { class: "hit", x: left - step / 2, y: top, width: right - left + step, height: bottom - top, tabindex: "0", "aria-label": "Line chart: use arrow keys to read values" });
  let current = -1;
  const place = (i, clientX, clientY) => {
    current = Math.max(0, Math.min(count - 1, i));
    const x = Math.round(xs(current)) + 0.5;
    cross.setAttribute("x1", x);
    cross.setAttribute("x2", x);
    cross.setAttribute("visibility", "visible");
    model.series.forEach((series, k) => {
      const v = series.values[current];
      const dot = hoverDots[k];
      if (typeof v === "number") {
        dot.setAttribute("cx", xs(current));
        dot.setAttribute("cy", ys(v));
        dot.setAttribute("visibility", "visible");
      } else dot.setAttribute("visibility", "hidden");
    });
    showTooltip(model.labels[current], seriesRows(model, current), clientX, clientY, true);
  };
  const off = () => {
    cross.setAttribute("visibility", "hidden");
    hoverDots.forEach((d) => d.setAttribute("visibility", "hidden"));
    hideTooltip();
  };
  overlay.addEventListener("pointermove", (e) => {
    const box = svg.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * width;
    place(Math.round((px - left) / (step || 1)), e.clientX, e.clientY);
  });
  overlay.addEventListener("pointerleave", off);
  overlay.addEventListener("blur", off);
  overlay.addEventListener("focus", () => {
    const [x, y] = focusPoint(overlay);
    place(current < 0 ? count - 1 : current, x, y);
  });
  overlay.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const box = svg.getBoundingClientRect();
    const next = current + (e.key === "ArrowRight" ? 1 : -1);
    const i = Math.max(0, Math.min(count - 1, next));
    place(i, box.left + (xs(i) / width) * box.width, box.top + 20);
  });
  svg.append(overlay);
  return svg;
}

// --- Public rendering -------------------------------------------------------------

/**
 * Render a chart model into `container`, re-rendering when the container resizes.
 * model: { labels, series: [{name, cls, values}], kind: 'hbar'|'column'|'line', stacked?, share?, clipped? }
 */
export function renderChart(container, model) {
  const root = h("div", { class: "viz" });
  container.replaceChildren(root);
  let lastWidth = 0;
  const draw = () => {
    const width = Math.floor(root.clientWidth);
    if (!width || width === lastWidth) return;
    lastWidth = width;
    const plot =
      model.kind === "line" ? drawLines(model, width)
        : model.kind === "column" ? drawColumns(model, width, model.stacked)
          : drawHBars(model, width);
    root.replaceChildren(
      ...[legend(model, model.kind === "line"), plot,
        model.clipped ? h("p", { class: "muted small", text: `Chart shows the first ${model.clipped} rows; the table has all of them.` }) : null,
      ].filter(Boolean),
    );
  };
  const observer = new ResizeObserver(() => requestAnimationFrame(draw));
  observer.observe(root);
  requestAnimationFrame(draw);
  return () => observer.disconnect();
}

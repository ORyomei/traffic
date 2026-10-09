const state = { index: null, repos: {}, repo: "", days: 90, sortKey: "views", sortDir: -1 };
const charts = {};
const fmt = new Intl.NumberFormat("ja-JP");
const $ = (id) => document.getElementById(id);

const DAY_MS = 86400000;
const isoDay = (d) => d.toISOString().slice(0, 10);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

async function load() {
  const res = await fetch("data/index.json", { cache: "no-cache" });
  if (!res.ok) throw new Error("data/index.json がまだありません");
  state.index = await res.json();
  const files = await Promise.all(state.index.repos.map((name) =>
    fetch(`data/repos/${encodeURIComponent(name)}.json`, { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))));
  state.index.repos.forEach((name, i) => { if (files[i]) state.repos[name] = files[i]; });

  $("owner").textContent = state.index.owner;
  $("updated").textContent = `最終更新: ${new Date(state.index.updated_at).toLocaleString("ja-JP")}`;
  const select = $("repo");
  for (const name of Object.keys(state.repos).sort()) select.add(new Option(name, name));

  const params = new URLSearchParams(location.hash.slice(1));
  if (params.get("repo") in state.repos) state.repo = params.get("repo");
  if (params.has("days")) state.days = Number(params.get("days")) || 0;
  render();
}

function dateRange() {
  const end = new Date(isoDay(new Date()));
  let start;
  if (state.days > 0) {
    start = new Date(end - (state.days - 1) * DAY_MS);
  } else {
    const all = Object.values(state.repos).flatMap((r) => Object.keys(r.views).concat(Object.keys(r.clones)));
    start = new Date(all.length ? all.sort()[0] : isoDay(end));
  }
  const days = [];
  for (let t = +start; t <= +end; t += DAY_MS) days.push(isoDay(new Date(t)));
  return days;
}

function series(repoNames, kind, days) {
  const count = days.map(() => 0), uniques = days.map(() => 0);
  for (const name of repoNames) {
    const daily = state.repos[name][kind];
    days.forEach((d, i) => {
      if (daily[d]) { count[i] += daily[d].count; uniques[i] += daily[d].uniques; }
    });
  }
  return { count, uniques };
}

const sum = (a) => a.reduce((x, y) => x + y, 0);

function render() {
  const sel = state.repo ? [state.repo] : Object.keys(state.repos);
  const days = dateRange();
  const views = series(sel, "views", days);
  const clones = series(sel, "clones", days);

  $("repo").value = state.repo;
  for (const b of $("range").querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(Number(b.dataset.days) === state.days));
  }
  history.replaceState(null, "", `#repo=${encodeURIComponent(state.repo)}&days=${state.days}`);

  $("kpi-views").textContent = fmt.format(sum(views.count));
  $("kpi-views-u").textContent = fmt.format(sum(views.uniques));
  $("kpi-clones").textContent = fmt.format(sum(clones.count));
  $("kpi-clones-u").textContent = fmt.format(sum(clones.uniques));

  drawChart("chart-views", days, views, ["Views", "Unique visitors"]);
  drawChart("chart-clones", days, clones, ["Clones", "Unique cloners"]);
  renderRepoTable(days);
  renderPopular(sel);
}

function drawChart(id, days, data, labels) {
  const grid = css("--grid"), muted = css("--muted"), axis = css("--axis");
  const colors = [css("--series-1"), css("--series-2")];
  const datasets = [data.count, data.uniques].map((values, i) => ({
    label: labels[i],
    data: values,
    borderColor: colors[i],
    backgroundColor: colors[i],
    borderWidth: 2,
    pointRadius: days.length <= 31 ? 2 : 0,
    pointHoverRadius: 5,
    pointHoverBorderWidth: 2,
    pointHoverBorderColor: css("--surface"),
    tension: 0,
  }));
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), {
    type: "line",
    data: { labels: days, datasets },
    options: {
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          align: "start",
          labels: { color: css("--text-2"), usePointStyle: true, pointStyle: "line", boxWidth: 16 },
        },
        tooltip: {
          backgroundColor: css("--surface"),
          titleColor: css("--text"),
          bodyColor: css("--text-2"),
          borderColor: css("--border"),
          borderWidth: 1,
          usePointStyle: true,
          callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt.format(c.parsed.y)}` },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: axis },
          ticks: { color: muted, maxRotation: 0, autoSkipPadding: 24, callback(v) { return this.getLabelForValue(v).slice(5); } },
        },
        y: {
          beginAtZero: true,
          grid: { color: grid },
          border: { display: false },
          ticks: { color: muted, precision: 0 },
        },
      },
    },
  });
}

function renderRepoTable(days) {
  const sparkDays = days.slice(-SPARK_DAYS);
  const rows = Object.keys(state.repos).map((name) => {
    const v = series([name], "views", days), c = series([name], "clones", days);
    return {
      name, views: sum(v.count), viewsU: sum(v.uniques), clones: sum(c.count), clonesU: sum(c.uniques),
      viewsDaily: series([name], "views", sparkDays).count,
      clonesDaily: series([name], "clones", sparkDays).count,
    };
  });
  const { sortKey: k, sortDir: dir } = state;
  rows.sort((a, b) => (k === "name" ? a.name.localeCompare(b.name) : a[k] - b[k]) * dir || a.name.localeCompare(b.name));

  for (const th of $("repo-table").querySelectorAll("th")) {
    th.setAttribute("aria-sort", th.dataset.key === k ? (dir < 0 ? "descending" : "ascending") : "none");
  }
  const tbody = $("repo-table").tBodies[0];
  tbody.replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    tr.className = r.name === state.repo ? "selected" : "";
    tr.dataset.repo = r.name;
    tr.append(
      cell(r.name),
      ...["views", "viewsU", "clones", "clonesU"].map((key) => cell(fmt.format(r[key]), "num")),
      sparkCell(r.viewsDaily, "--series-1", "Views"),
      sparkCell(r.clonesDaily, "--series-1", "Clones"),
    );
    return tr;
  }));
}

const SVG_NS = "http://www.w3.org/2000/svg";
const SPARK_W = 120, SPARK_H = 28, SPARK_DAYS = 30;

// Each sparkline has its own y-scale so the shape is visible even for quiet repos.
function sparkCell(values, colorVar, label) {
  const td = document.createElement("td");
  td.className = "spark";
  const max = Math.max(...values);
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${SPARK_W} ${SPARK_H}`);
  svg.setAttribute("width", SPARK_W);
  svg.setAttribute("height", SPARK_H);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${label} 直近${SPARK_DAYS}日（最大 ${max}/日）`);
  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = `${label} 直近${SPARK_DAYS}日: 最大 ${fmt.format(max)}/日`;

  const step = values.length > 1 ? SPARK_W / (values.length - 1) : 0;
  const y = (v) => SPARK_H - 1 - (max ? (v / max) * (SPARK_H - 3) : 0);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`);

  const area = document.createElementNS(SVG_NS, "polygon");
  area.setAttribute("points", `0,${SPARK_H - 1} ${pts.join(" ")} ${SPARK_W},${SPARK_H - 1}`);
  area.setAttribute("fill", max ? `var(${colorVar})` : "none");
  area.setAttribute("fill-opacity", "0.12");
  const line = document.createElementNS(SVG_NS, "polyline");
  line.setAttribute("points", pts.join(" "));
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", max ? `var(${colorVar})` : "var(--axis)");
  line.setAttribute("stroke-width", "1.5");
  line.setAttribute("stroke-linejoin", "round");
  line.setAttribute("vector-effect", "non-scaling-stroke");

  svg.append(title, area, line);
  td.append(svg);
  return td;
}

function latestSnapshot(repo, key) {
  const snaps = state.repos[repo][key];
  const latest = Object.keys(snaps).sort().pop();
  return latest ? snaps[latest] : [];
}

function renderPopular(sel) {
  const refs = new Map(), paths = new Map();
  for (const name of sel) {
    for (const r of latestSnapshot(name, "referrers")) {
      const e = refs.get(r.referrer) || { label: r.referrer, count: 0, uniques: 0 };
      e.count += r.count; e.uniques += r.uniques;
      refs.set(r.referrer, e);
    }
    for (const p of latestSnapshot(name, "paths")) {
      paths.set(p.path, { label: p.path, title: p.title, count: p.count, uniques: p.uniques });
    }
  }
  fillTable("referrers", [...refs.values()]);
  fillTable("paths", [...paths.values()], true);
}

function fillTable(id, items, isPath = false) {
  items.sort((a, b) => b.count - a.count);
  const tbody = $(id).tBodies[0];
  if (!items.length) {
    const td = cell("データなし", "empty");
    td.colSpan = 3;
    const tr = document.createElement("tr");
    tr.append(td);
    tbody.replaceChildren(tr);
    return;
  }
  tbody.replaceChildren(...items.slice(0, 10).map((it) => {
    const tr = document.createElement("tr");
    const label = cell(it.label, isPath ? "path" : "");
    if (isPath) {
      const a = document.createElement("a");
      a.href = `https://github.com${it.label}`;
      a.textContent = it.label;
      a.title = it.title;
      label.replaceChildren(a);
    }
    tr.append(label, cell(fmt.format(it.count), "num"), cell(fmt.format(it.uniques), "num"));
    return tr;
  }));
}

function cell(text, cls = "") {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

$("repo").addEventListener("change", (e) => { state.repo = e.target.value; render(); });
$("range").addEventListener("click", (e) => {
  if (!e.target.dataset.days) return;
  state.days = Number(e.target.dataset.days);
  render();
});
$("repo-table").tHead.addEventListener("click", (e) => {
  const key = e.target.dataset.key;
  if (!key) return;
  if (state.sortKey === key) state.sortDir *= -1;
  else { state.sortKey = key; state.sortDir = key === "name" ? 1 : -1; }
  render();
});
$("repo-table").tBodies[0].addEventListener("click", (e) => {
  const tr = e.target.closest("tr");
  if (!tr?.dataset.repo) return;
  state.repo = state.repo === tr.dataset.repo ? "" : tr.dataset.repo;
  render();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => state.index && render());

load().catch((err) => { $("updated").textContent = err.message; });

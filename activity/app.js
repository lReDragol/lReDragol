const DATA_URL = "../profile/activity-data.json";
const metrics = new Set(["commits", "changed", "additions", "deletions"]);
const number = new Intl.NumberFormat("en-US");
const fullDate = new Intl.DateTimeFormat("en", { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
const monthName = new Intl.DateTimeFormat("en", { month: "short", timeZone: "UTC" });

const state = { data: null, metric: "commits", range: 365 };
const heatmap = document.querySelector("#heatmap");
const months = document.querySelector("#months");
const tooltip = document.querySelector("#tooltip");

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function dateKey(value) {
  return value.toISOString().slice(0, 10);
}

function addDays(value, days) {
  const result = new Date(value);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}

function levelFor(value, maximum) {
  if (!value || !maximum) return 0;
  const ratio = value / maximum;
  if (ratio <= 0.15) return 1;
  if (ratio <= 0.35) return 2;
  if (ratio <= 0.65) return 3;
  return 4;
}

function selectedDays() {
  return state.data.days.slice(-Math.min(state.range, state.data.days.length));
}

function totals(days) {
  return days.reduce((sum, day) => {
    for (const key of ["commits", "additions", "deletions", "changed", "merges"]) {
      sum[key] += Number(day[key] || 0);
    }
    return sum;
  }, { commits: 0, additions: 0, deletions: 0, changed: 0, merges: 0 });
}

function showTooltip(day, event) {
  tooltip.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = fullDate.format(parseDate(day.date));
  tooltip.append(heading);

  const list = document.createElement("dl");
  const rows = [
    ["Commits", day.commits],
    ["Added", `+${number.format(day.additions)}`],
    ["Deleted", `-${number.format(day.deletions)}`],
    ["Changed", number.format(day.changed)],
    ["Merge commits", number.format(day.merges || 0)],
  ];
  for (const [label, value] of rows) {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = String(value);
    list.append(term, detail);
  }
  tooltip.append(list);
  tooltip.hidden = false;
  positionTooltip(event);
}

function positionTooltip(event) {
  if (tooltip.hidden) return;
  const fallback = event.currentTarget?.getBoundingClientRect();
  const pointerX = Number.isFinite(event.clientX) && event.clientX > 0 ? event.clientX : (fallback?.left || 0) + 8;
  const pointerY = Number.isFinite(event.clientY) && event.clientY > 0 ? event.clientY : (fallback?.top || 0) + 8;
  const width = tooltip.offsetWidth;
  const height = tooltip.offsetHeight;
  const left = Math.min(pointerX + 14, window.innerWidth - width - 10);
  const top = pointerY + height + 18 < window.innerHeight ? pointerY + 14 : pointerY - height - 14;
  tooltip.style.left = `${Math.max(10, left)}px`;
  tooltip.style.top = `${Math.max(10, top)}px`;
}

function render() {
  const days = selectedDays();
  const summary = totals(days);
  document.querySelector("#total-commits").textContent = number.format(summary.commits);
  document.querySelector("#total-additions").textContent = `+${number.format(summary.additions)}`;
  document.querySelector("#total-deletions").textContent = `-${number.format(summary.deletions)}`;
  document.querySelector("#total-changed").textContent = number.format(summary.changed);

  heatmap.replaceChildren();
  months.replaceChildren();
  if (!days.length) return;

  const first = parseDate(days[0].date);
  const gridStart = addDays(first, -first.getUTCDay());
  const maximum = Math.max(...days.map((day) => Number(day[state.metric] || 0)), 0);
  const seenMonths = new Set();

  for (const day of days) {
    const date = parseDate(day.date);
    const deltaDays = Math.round((date - gridStart) / 86400000);
    const week = Math.floor(deltaDays / 7);
    const weekday = deltaDays % 7;
    const cell = document.createElement("button");
    const value = Number(day[state.metric] || 0);
    cell.type = "button";
    cell.className = "day";
    cell.dataset.level = String(levelFor(value, maximum));
    cell.style.gridColumn = String(week + 1);
    cell.style.gridRow = String(weekday + 1);
    cell.setAttribute("role", "gridcell");
    cell.setAttribute("aria-label", `${fullDate.format(date)}: ${day.commits} commits, ${day.additions} additions, ${day.deletions} deletions`);
    cell.addEventListener("mouseenter", (event) => showTooltip(day, event));
    cell.addEventListener("mousemove", positionTooltip);
    cell.addEventListener("mouseleave", () => { tooltip.hidden = true; });
    cell.addEventListener("focus", (event) => showTooltip(day, event));
    cell.addEventListener("blur", () => { tooltip.hidden = true; });
    heatmap.append(cell);

    const monthKey = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
    if (!seenMonths.has(monthKey)) {
      seenMonths.add(monthKey);
      const label = document.createElement("span");
      label.textContent = monthName.format(date);
      label.style.left = `${week * 17}px`;
      months.append(label);
    }
  }

  const start = fullDate.format(parseDate(days[0].date));
  const end = fullDate.format(parseDate(days.at(-1).date));
  document.querySelector("#period-label").textContent = `${start} - ${end} | color: ${state.metric}`;
}

function wireControls(containerSelector, dataKey, stateKey, validValues) {
  document.querySelector(containerSelector).addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const raw = button.dataset[dataKey];
    const value = stateKey === "range" ? Number(raw) : raw;
    if (!validValues.has(value)) return;
    state[stateKey] = value;
    for (const peer of button.parentElement.querySelectorAll("button")) peer.classList.toggle("active", peer === button);
    render();
  });
}

async function start() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.days)) throw new Error("Invalid activity data");
    state.data = data;
    document.querySelector("#generated-at").textContent = `Updated ${data.generated_at} | ${data.timezone}`;
    render();
  } catch (error) {
    heatmap.className = "error";
    heatmap.textContent = `Could not load activity data: ${error.message}`;
    document.querySelector("#period-label").textContent = "Data unavailable";
  }
}

wireControls("#metric-controls", "metric", "metric", metrics);
wireControls("#range-controls", "range", "range", new Set([30, 90, 365]));
start();

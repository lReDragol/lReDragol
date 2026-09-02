const DATA_URL = "../profile/activity-data.json";
const RELEASES_DATA_URL = "../profile/releases-data.json";
const metrics = new Set(["commits", "changed", "additions", "deletions"]);
const number = new Intl.NumberFormat("en-US");
const fullDate = new Intl.DateTimeFormat("en", { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
const monthName = new Intl.DateTimeFormat("en", { month: "short", timeZone: "UTC" });

const state = { data: null, releases: null, metric: "commits", range: 365, selectedDate: null, previewDate: null };
const heatmap = document.querySelector("#heatmap");
const months = document.querySelector("#months");
const tooltip = document.querySelector("#tooltip");
const repositoryList = document.querySelector("#repository-list");
const repositoryReset = document.querySelector("#repository-reset");

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

function aggregateRepositories(days) {
  const repositories = new Map();
  for (const day of days) {
    if (!Array.isArray(day.repositories)) continue;
    for (const repository of day.repositories) {
      if (!repository || typeof repository.id !== "string" || typeof repository.name !== "string") continue;
      if (!repositories.has(repository.id)) {
        repositories.set(repository.id, {
          id: repository.id,
          name: repository.name,
          url: repository.url,
          private: repository.private === true,
          commits: 0,
          additions: 0,
          deletions: 0,
          changed: 0,
          merges: 0,
        });
      }
      const aggregate = repositories.get(repository.id);
      for (const key of ["commits", "additions", "deletions", "changed", "merges"]) {
        aggregate[key] += Number(repository[key] || 0);
      }
    }
  }
  return [...repositories.values()].sort((left, right) =>
    right.commits - left.commits || right.changed - left.changed || left.name.localeCompare(right.name)
  );
}

function repositoryView() {
  const days = selectedDays();
  const activeDate = state.previewDate || state.selectedDate;
  const activeDay = activeDate ? days.find((day) => day.date === activeDate) : null;
  return { days: activeDay ? [activeDay] : days, activeDay };
}

function renderRepositoryActivity() {
  const { days, activeDay } = repositoryView();
  const repositories = aggregateRepositories(days);
  const summary = totals(days);
  const commitLabel = summary.commits === 1 ? "commit" : "commits";
  const repositoryLabel = repositories.length === 1 ? "repository" : "repositories";
  document.querySelector("#repository-activity-heading").textContent =
    `Created ${number.format(summary.commits)} ${commitLabel} in ${number.format(repositories.length)} ${repositoryLabel}`;
  document.querySelector("#repository-context").textContent = activeDay
    ? fullDate.format(parseDate(activeDay.date))
    : `${fullDate.format(parseDate(days[0].date))} - ${fullDate.format(parseDate(days.at(-1).date))}`;
  repositoryReset.hidden = !state.selectedDate;
  repositoryList.replaceChildren();

  if (!repositories.length) {
    const empty = document.createElement("p");
    empty.className = "repository-empty";
    empty.textContent = "No authored commits for this selection.";
    repositoryList.append(empty);
    return;
  }

  const maximum = Math.max(...repositories.map((repository) => repository.commits), 1);
  for (const repository of repositories) {
    const row = document.createElement("div");
    row.className = "repository-row";

    const url = safeGitHubUrl(repository.url);
    const name = document.createElement(url === "#" || repository.private ? "span" : "a");
    name.className = `repository-name${repository.private ? " private" : ""}`;
    name.textContent = repository.name;
    if (name instanceof HTMLAnchorElement) {
      name.href = url;
      name.target = "_blank";
      name.rel = "noreferrer";
    }

    const track = document.createElement("span");
    track.className = "repository-bar-track";
    const fill = document.createElement("span");
    fill.className = "repository-bar-fill";
    fill.style.setProperty("--bar-width", `${(repository.commits / maximum) * 100}%`);
    track.append(fill);

    const values = document.createElement("span");
    values.className = "repository-values";
    const commits = document.createElement("strong");
    commits.textContent = `${number.format(repository.commits)} ${repository.commits === 1 ? "commit" : "commits"}`;
    values.append(commits, ` | +${number.format(repository.additions)} / -${number.format(repository.deletions)} lines`);
    row.append(name, track, values);
    repositoryList.append(row);
  }
}

function showDetailsTooltip(title, rows, event) {
  tooltip.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = title;
  tooltip.append(heading);

  const list = document.createElement("dl");
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

function showActivityTooltip(day, event) {
  showDetailsTooltip(fullDate.format(parseDate(day.date)), [
    ["Commits", day.commits],
    ["Added", `+${number.format(day.additions)}`],
    ["Deleted", `-${number.format(day.deletions)}`],
    ["Changed", number.format(day.changed)],
    ["Merge commits", number.format(day.merges || 0)],
  ], event);
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
  if (!days.length) {
    repositoryList.replaceChildren();
    return;
  }

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
    cell.dataset.date = day.date;
    cell.dataset.level = String(levelFor(value, maximum));
    cell.classList.toggle("selected", state.selectedDate === day.date);
    cell.style.gridColumn = String(week + 1);
    cell.style.gridRow = String(weekday + 1);
    cell.setAttribute("role", "gridcell");
    cell.setAttribute("aria-label", `${fullDate.format(date)}: ${day.commits} commits, ${day.additions} additions, ${day.deletions} deletions`);
    cell.addEventListener("mouseenter", (event) => {
      state.previewDate = day.date;
      renderRepositoryActivity();
      showActivityTooltip(day, event);
    });
    cell.addEventListener("mousemove", positionTooltip);
    cell.addEventListener("mouseleave", () => {
      state.previewDate = null;
      tooltip.hidden = true;
      renderRepositoryActivity();
    });
    cell.addEventListener("focus", (event) => {
      state.previewDate = day.date;
      renderRepositoryActivity();
      showActivityTooltip(day, event);
    });
    cell.addEventListener("blur", () => {
      state.previewDate = null;
      tooltip.hidden = true;
      renderRepositoryActivity();
    });
    cell.addEventListener("click", () => {
      state.selectedDate = state.selectedDate === day.date ? null : day.date;
      state.previewDate = null;
      for (const peer of heatmap.querySelectorAll(".day")) {
        peer.classList.toggle("selected", peer.dataset.date === state.selectedDate);
      }
      renderRepositoryActivity();
    });
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
  renderRepositoryActivity();
}

function safeGitHubUrl(value) {
  return typeof value === "string" && value.startsWith("https://github.com/") ? value : "#";
}

function releaseDelta(history) {
  if (!Array.isArray(history) || history.length < 2) return "Daily download history begins with this snapshot.";
  const current = Number(history.at(-1).downloads || 0);
  const previous = Number(history.at(-2).downloads || 0);
  const delta = current - previous;
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${number.format(delta)} downloads since the previous daily snapshot.`;
}

function wireReleaseTooltip(element, title, rows) {
  element.addEventListener("mouseenter", (event) => showDetailsTooltip(title, rows, event));
  element.addEventListener("mousemove", positionTooltip);
  element.addEventListener("mouseleave", () => { tooltip.hidden = true; });
  element.addEventListener("focus", (event) => showDetailsTooltip(title, rows, event));
  element.addEventListener("blur", () => { tooltip.hidden = true; });
}

function renderReleases() {
  const data = state.releases;
  const totals = data.totals || {};
  document.querySelector("#release-downloads").textContent = number.format(totals.downloads || 0);
  document.querySelector("#release-projects").textContent = number.format(totals.repositories_with_downloads || 0);
  document.querySelector("#release-count").textContent = number.format(totals.releases || 0);
  document.querySelector("#release-assets").textContent = number.format(totals.assets || 0);
  document.querySelector("#release-generated-at").textContent = `Updated ${data.generated_at}`;
  document.querySelector("#release-delta").textContent = releaseDelta(data.history);

  const repositories = Array.isArray(data.repositories) ? data.repositories.filter((repo) => Number(repo.downloads || 0) > 0) : [];
  const maxDownloads = Math.max(...repositories.map((repo) => Number(repo.downloads || 0)), 1);
  const maxLog = Math.log1p(maxDownloads);
  const bars = document.querySelector("#release-bars");
  bars.replaceChildren();

  for (const repo of repositories) {
    const row = document.createElement("a");
    row.className = "release-row";
    row.href = safeGitHubUrl(repo.url);
    row.target = "_blank";
    row.rel = "noreferrer";

    const name = document.createElement("span");
    name.className = "release-name";
    name.textContent = repo.name;
    const track = document.createElement("span");
    track.className = "bar-track";
    const fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.setProperty("--bar-width", `${(Math.log1p(Number(repo.downloads || 0)) / maxLog) * 100}%`);
    track.append(fill);
    const value = document.createElement("span");
    value.className = "release-value";
    value.textContent = number.format(repo.downloads || 0);
    row.append(name, track, value);
    wireReleaseTooltip(row, repo.name, [
      ["Downloads", number.format(repo.downloads || 0)],
      ["Releases", number.format(repo.releases || 0)],
      ["Assets", number.format(repo.assets || 0)],
      ["Latest release", repo.latest_release || "-"],
    ]);
    bars.append(row);
  }

  const assetRows = document.querySelector("#asset-rows");
  assetRows.replaceChildren();
  const assets = Array.isArray(data.assets) ? data.assets.slice(0, 12) : [];
  for (const asset of assets) {
    const row = document.createElement("tr");
    const assetCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = safeGitHubUrl(asset.url);
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = asset.name;
    assetCell.append(link);
    const repoCell = document.createElement("td");
    repoCell.className = "asset-repo";
    repoCell.textContent = asset.repository;
    const downloadsCell = document.createElement("td");
    downloadsCell.className = "asset-downloads";
    downloadsCell.textContent = number.format(asset.downloads || 0);
    row.append(assetCell, repoCell, downloadsCell);
    wireReleaseTooltip(link, asset.name, [
      ["Repository", asset.repository],
      ["Release", asset.release],
      ["Downloads", number.format(asset.downloads || 0)],
      ["Size", `${number.format(asset.size || 0)} bytes`],
    ]);
    assetRows.append(row);
  }
}

function wireControls(containerSelector, dataKey, stateKey, validValues) {
  document.querySelector(containerSelector).addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const raw = button.dataset[dataKey];
    const value = stateKey === "range" ? Number(raw) : raw;
    if (!validValues.has(value)) return;
    state[stateKey] = value;
    if (stateKey === "range") {
      state.selectedDate = null;
      state.previewDate = null;
    }
    for (const peer of button.parentElement.querySelectorAll("button")) peer.classList.toggle("active", peer === button);
    render();
  });
}

async function loadActivity() {
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

async function loadReleases() {
  try {
    const response = await fetch(RELEASES_DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data.totals || !Array.isArray(data.repositories) || !Array.isArray(data.assets)) throw new Error("Invalid release data");
    state.releases = data;
    renderReleases();
  } catch (error) {
    document.querySelector("#release-generated-at").textContent = `Could not load release data: ${error.message}`;
    document.querySelector("#release-bars").className = "error";
    document.querySelector("#release-bars").textContent = "Release data unavailable";
  }
}

wireControls("#metric-controls", "metric", "metric", metrics);
wireControls("#range-controls", "range", "range", new Set([30, 90, 365]));
repositoryReset.addEventListener("click", () => {
  state.selectedDate = null;
  state.previewDate = null;
  render();
});
loadActivity();
loadReleases();

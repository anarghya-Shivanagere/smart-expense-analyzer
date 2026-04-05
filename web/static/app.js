const state = {
  categories: [],
  datasets: [],
  months: [],
  selectedDataset: null,
  result: null,
  editedTransactions: [],
  reviewSelections: new Map(),
  activeCategoryFilter: null,
  activeMerchantFilter: null,
};

const els = {
  datasetSelect: document.getElementById("dataset-select"),
  monthSelect: document.getElementById("month-select"),
  seedInput: document.getElementById("seed-input"),
  uploadInput: document.getElementById("upload-input"),
  uploadBtn: document.getElementById("upload-btn"),
  analyzeBtn: document.getElementById("analyze-btn"),
  saveCorrectionsBtn: document.getElementById("save-corrections-btn"),
  saveFeedbackBtn: document.getElementById("save-feedback-btn"),
  statusBanner: document.getElementById("status-banner"),
  snapshotPanel: document.getElementById("snapshot-panel"),
  resultsPanel: document.getElementById("results-panel"),
  metricState: document.getElementById("metric-state"),
  metricTransactions: document.getElementById("metric-transactions"),
  metricAnomalies: document.getElementById("metric-anomalies"),
  metricSpend: document.getElementById("metric-spend"),
  activeFilters: document.getElementById("active-filters"),
  categoryBars: document.getElementById("category-bars"),
  categoryDonut: document.getElementById("category-donut"),
  recurringList: document.getElementById("recurring-list"),
  reportChips: document.getElementById("report-chips"),
  reportBox: document.getElementById("report-box"),
  exportsGrid: document.getElementById("exports-grid"),
  transactionsCategoryFilter: document.getElementById("transactions-category-filter"),
  transactionsCount: document.getElementById("transactions-count"),
  transactionsTable: document.querySelector("#transactions-table tbody"),
  anomaliesTable: document.querySelector("#anomalies-table tbody"),
  transitionsTable: document.querySelector("#transitions-table tbody"),
  traceTable: document.querySelector("#trace-table tbody"),
  tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
  tabPanels: Array.from(document.querySelectorAll(".tab-content")),
};

const CHART_COLORS = ["#63c4ff", "#45e0b1", "#8be37f", "#ffbf69", "#ff8fa9", "#9d8cff", "#7ad5ff", "#68efda"];
const SOURCE_LABELS = {
  input: "CSV Input",
  memory: "Learned Merchant",
  learned: "Similarity Match",
  ml: "ML Classifier",
  rules: "Keyword Rule",
  fallback: "Fallback",
  manual: "Manual Override",
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Something went wrong.");
  }
  return response.json();
}

function setStatus(message, tone = "muted") {
  els.statusBanner.textContent = message;
  els.statusBanner.className = `status-banner ${tone}`;
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function getSourceLabel(source) {
  return SOURCE_LABELS[String(source || "").toLowerCase()] || source || "-";
}

function getConfidenceMeta(score) {
  const value = Number(score || 0);
  if (value >= 0.9) return { label: "High", tone: "high", value };
  if (value >= 0.7) return { label: "Medium", tone: "medium", value };
  return { label: "Low", tone: "low", value };
}

function getConfidenceHelp(source, confidence) {
  const sourceLabel = getSourceLabel(source);
  const value = Number(confidence || 0).toFixed(2);
  switch (String(source || "").toLowerCase()) {
    case "input":
      return `${sourceLabel}: taken directly from the uploaded CSV (${value}).`;
    case "memory":
      return `${sourceLabel}: reused from a saved merchant match and adjusted by how often that merchant has been seen (${value}).`;
    case "learned":
      return `${sourceLabel}: inferred from similar labeled transactions in this dataset (${value}).`;
    case "rules":
      return `${sourceLabel}: based on matched category keywords in the description; more matches increase confidence (${value}).`;
    case "ml":
      return `${sourceLabel}: predicted by the local probabilistic classifier trained on seeded category examples and known transactions (${value}).`;
    case "fallback":
      return `${sourceLabel}: no stronger signal was found, so this should be reviewed (${value}).`;
    case "manual":
      return `${sourceLabel}: saved from a manual category correction (${value}).`;
    default:
      return `${sourceLabel}: confidence ${value}.`;
  }
}

function populateSelect(select, values, selectedValue, includeAll = false) {
  select.innerHTML = "";
  const items = includeAll ? ["All", ...values] : values;
  items.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === selectedValue;
    select.appendChild(option);
  });
}

function activateTab(tabName) {
  els.tabButtons.forEach((button) => button.classList.toggle("active", button.dataset.tab === tabName));
  els.tabPanels.forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === tabName));
}

async function loadMonths(dataset) {
  if (!dataset) return [];
  const payload = await api(`/api/datasets/${encodeURIComponent(dataset)}/months`);
  return payload.months || [];
}

async function refreshBootstrap(preferredDataset = null) {
  const payload = await api("/api/bootstrap");
  state.datasets = payload.datasets || [];
  state.categories = payload.categories || [];
  state.selectedDataset = preferredDataset || payload.default_dataset || state.datasets[0] || null;
  state.months = state.selectedDataset ? await loadMonths(state.selectedDataset) : [];
  populateSelect(els.datasetSelect, state.datasets, state.selectedDataset);
  populateSelect(els.monthSelect, state.months, "All", true);
}

function getResultRows() {
  return state.result?.categorized_transactions || [];
}

function getCategoryRows(rows) {
  const totals = new Map();
  rows.forEach((row) => {
    const category = row.category || "Other";
    const amount = Math.abs(Number(row.amount || 0));
    totals.set(category, (totals.get(category) || 0) + amount);
  });
  return Array.from(totals.entries())
    .map(([category, amount]) => ({ category, amount }))
    .sort((left, right) => right.amount - left.amount);
}

function getFilteredTransactions(rows) {
  return rows.filter((row) => {
    const categoryMatch = !state.activeCategoryFilter || (row.category || "Other") === state.activeCategoryFilter;
    const merchantMatch = !state.activeMerchantFilter || (row.merchant || row.description || "") === state.activeMerchantFilter;
    return categoryMatch && merchantMatch;
  });
}

function buildFilterEntries() {
  const entries = [];
  if (state.activeCategoryFilter) entries.push({ label: "Category", value: state.activeCategoryFilter, key: "category" });
  if (state.activeMerchantFilter) entries.push({ label: "Merchant", value: state.activeMerchantFilter, key: "merchant" });
  return entries;
}

function clearFilter(mode) {
  if (mode === "category" || mode === "all") state.activeCategoryFilter = null;
  if (mode === "merchant" || mode === "all") state.activeMerchantFilter = null;
}

function setCategoryFilter(category) {
  state.activeCategoryFilter = state.activeCategoryFilter === category ? null : category;
  state.activeMerchantFilter = null;
}

function setMerchantFilter(merchant) {
  state.activeMerchantFilter = state.activeMerchantFilter === merchant ? null : merchant;
  state.activeCategoryFilter = null;
}

function renderFilteredTransactions() {
  const rows = getFilteredTransactions(getResultRows());
  renderTransactions(rows);
  renderTransactionFilter();
  renderTransactionsCount(rows);
}

function renderTransactionFilter() {
  const categories = Array.from(new Set(getResultRows().map((row) => row.category || "Other"))).sort((a, b) => a.localeCompare(b));
  populateSelect(els.transactionsCategoryFilter, categories, state.activeCategoryFilter || "All", true);
}

function renderTransactionsCount(rows) {
  const total = getResultRows().length;
  const count = rows.length;
  els.transactionsCount.textContent =
    count === total
      ? `Showing all ${formatNumber(total)} transactions`
      : `Showing ${formatNumber(count)} of ${formatNumber(total)} transactions`;
}

function refreshFilteredView(statusMessage = "") {
  if (!state.result) return;
  renderFilteredTransactions();
  renderActiveFilters();
  if (statusMessage) setStatus(statusMessage, "success");
}

function renderActiveFilters() {
  const entries = buildFilterEntries();
  if (!entries.length) {
    els.activeFilters.innerHTML = "";
    els.activeFilters.classList.add("hidden");
    return;
  }

  els.activeFilters.classList.remove("hidden");
  els.activeFilters.innerHTML = `
    <div class="filter-banner-copy">
      <strong>Active Filter${entries.length > 1 ? "s" : ""}</strong>
      <span>${entries.map((entry) => `${entry.label}: ${entry.value}`).join(" | ")}</span>
    </div>
    <div class="filter-banner-actions">
      ${entries
        .map((entry) => `<button type="button" class="filter-pill" data-clear-filter="${entry.key}">Clear ${entry.label}</button>`)
        .join("")}
      <button type="button" class="filter-pill clear-all" data-clear-filter="all">Clear All</button>
    </div>
  `;

  els.activeFilters.querySelectorAll("[data-clear-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      clearFilter(button.dataset.clearFilter);
      refreshFilteredView("Filters cleared.");
      renderOverview(state.result);
    });
  });
}

function renderBars(rows) {
  els.categoryBars.innerHTML = "";
  if (!rows.length) {
    els.categoryBars.innerHTML = '<div class="meta">No category totals available for this selection.</div>';
    return;
  }

  const maxAmount = Math.max(...rows.map((row) => row.amount), 1);
  rows.forEach((row) => {
    const wrapper = document.createElement("div");
    wrapper.className = "bar-row";
    wrapper.innerHTML = `
      <div class="bar-meta">
        <span>${row.category}</span>
        <span>${formatCurrency(row.amount)}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${Math.max((row.amount / maxAmount) * 100, 4)}%"></div>
      </div>
    `;
    els.categoryBars.appendChild(wrapper);
  });
}

function renderDonut(rows) {
  els.categoryDonut.innerHTML = "";
  if (!rows.length) {
    els.categoryDonut.innerHTML = '<div class="meta">Category mix will appear after analysis.</div>';
    return;
  }

  const total = rows.reduce((sum, row) => sum + row.amount, 0) || 1;
  const size = 220;
  const center = size / 2;
  const radius = 72;
  const strokeWidth = 24;
  const circumference = 2 * Math.PI * radius;
  let startPercent = 0;

  const segments = rows.map((row, index) => {
    const percentage = (row.amount / total) * 100;
    const dashLength = (percentage / 100) * circumference;
    const dashOffset = -((startPercent / 100) * circumference);
    const color = CHART_COLORS[index % CHART_COLORS.length];
    startPercent += percentage;
    return { ...row, percentage, dashLength, dashOffset, color };
  });

  const donut = document.createElement("div");
  donut.className = "donut-chart";
  donut.innerHTML = `
    <svg class="donut-svg" viewBox="0 0 ${size} ${size}" role="img" aria-label="Spend by category donut chart">
      <circle cx="${center}" cy="${center}" r="${radius}" stroke="rgba(255,255,255,0.06)" stroke-width="${strokeWidth}" fill="none"></circle>
      ${segments
        .map(
          (segment, index) => `
            <circle
              class="donut-segment"
              data-segment-index="${index}"
              cx="${center}"
              cy="${center}"
              r="${radius}"
              stroke="${segment.color}"
              stroke-width="${strokeWidth}"
              stroke-dasharray="${segment.dashLength} ${circumference}"
              stroke-dashoffset="${segment.dashOffset}"
            ></circle>`,
        )
        .join("")}
      <circle class="donut-hole" cx="${center}" cy="${center}" r="${radius - strokeWidth / 2 - 4}"></circle>
    </svg>
    <div class="donut-center"><div><strong></strong><span></span></div></div>
    <div class="donut-tooltip"></div>
  `;

  const centerTitle = donut.querySelector("strong");
  const centerText = donut.querySelector("span");
  const tooltip = donut.querySelector(".donut-tooltip");
  const segmentNodes = Array.from(donut.querySelectorAll(".donut-segment"));
  const legend = document.createElement("div");
  legend.className = "legend-list";

  const setActiveSegment = (segment, activeRow = null) => {
    centerTitle.textContent = segment.category;
    centerText.textContent = `${formatCurrency(segment.amount)} | ${segment.percentage.toFixed(1)}% of total`;
    tooltip.textContent = `${segment.category}: ${formatCurrency(segment.amount)} (${segment.percentage.toFixed(1)}%)`;
    tooltip.classList.add("visible");
    donut.classList.add("active");
    legend.querySelectorAll(".legend-row").forEach((row) => row.classList.toggle("active", row === activeRow));
    segmentNodes.forEach((node, index) => node.classList.toggle("active", segments[index] === segment));
  };

  const syncSelectedCategory = () => {
    legend.querySelectorAll(".legend-row").forEach((row) => row.classList.toggle("selected", row.dataset.category === state.activeCategoryFilter));
    segmentNodes.forEach((node, index) => node.classList.toggle("selected", segments[index].category === state.activeCategoryFilter));
  };

  const applyCategoryFilter = (segment) => {
    setCategoryFilter(segment.category);
    refreshFilteredView(state.activeCategoryFilter ? `Showing only ${state.activeCategoryFilter} transactions.` : "Showing all transactions.");
    activateTab("transactions");
    syncSelectedCategory();
  };

  segments.forEach((segment) => {
    const row = document.createElement("div");
    row.className = "legend-row";
    row.tabIndex = 0;
    row.dataset.category = segment.category;
    row.innerHTML = `
      <div class="legend-label">
        <span class="legend-swatch" style="background:${segment.color}"></span>
        <span>${segment.category}</span>
      </div>
      <div class="meta">${segment.percentage.toFixed(0)}%</div>
    `;
    row.addEventListener("mouseenter", () => setActiveSegment(segment, row));
    row.addEventListener("focus", () => setActiveSegment(segment, row));
    row.addEventListener("click", () => applyCategoryFilter(segment));
    legend.appendChild(row);
  });

  segmentNodes.forEach((node, index) => {
    node.addEventListener("mouseenter", () => setActiveSegment(segments[index]));
    node.addEventListener("focus", () => setActiveSegment(segments[index]));
    node.addEventListener("click", () => applyCategoryFilter(segments[index]));
  });

  setActiveSegment(segments[0]);
  syncSelectedCategory();
  requestAnimationFrame(() => {
    segmentNodes.forEach((node, index) => {
      node.style.animationDelay = `${index * 70}ms`;
      node.classList.add("animate-in");
    });
  });

  els.categoryDonut.appendChild(donut);
  els.categoryDonut.appendChild(legend);
}

function renderRecurring(items) {
  els.recurringList.innerHTML = "";
  if (!items.length) {
    els.recurringList.innerHTML = '<div class="meta">No recurring expenses detected in this run.</div>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "list-card";
    card.tabIndex = 0;
    card.innerHTML = `
      <strong>${item.merchant}</strong>
      <div class="meta">${item.category} | repeats ${item.occurrence_count} times | avg ${formatCurrency(item.average_amount)}</div>
      <div class="meta">Cadence ${item.cadence_days || "calendar-like"} days</div>
    `;
    const handleSelect = () => {
      setMerchantFilter(item.merchant);
      refreshFilteredView(state.activeMerchantFilter ? `Showing transactions for ${state.activeMerchantFilter}.` : "Showing all transactions.");
      activateTab("transactions");
    };
    card.addEventListener("click", handleSelect);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handleSelect();
      }
    });
    els.recurringList.appendChild(card);
  });
}

function renderReportChips(result, categoryRows) {
  els.reportChips.innerHTML = "";
  const topThree = categoryRows.slice(0, 3).map((row) => row.category).join(", ") || "Not enough data";
  [
    ["Run State", result.state || "-"],
    ["Total Spend", formatCurrency(result.metrics?.total_spend || 0)],
    ["Transactions", formatNumber(result.metrics?.total_transactions || 0)],
    ["Top Categories", topThree],
  ].forEach(([label, value]) => {
    const chip = document.createElement("div");
    chip.className = "report-chip";
    chip.innerHTML = `<span class="label">${label}</span><span class="value">${value}</span>`;
    els.reportChips.appendChild(chip);
  });
}

function renderExports(result) {
  els.exportsGrid.innerHTML = "";
  [
    ["Categorized CSV", result.categorized_csv_path],
    ["Merchant Summary CSV", result.merchant_summary_csv_path],
    ["Anomalies CSV", result.anomalies_csv_path],
    ["Summary JSON", result.summary_json_path],
    ["Report TXT", result.report_path],
  ].forEach(([label, path]) => {
    const row = document.createElement("div");
    row.className = "export-item";
    row.innerHTML = `<span>${label}</span><a href="/api/download?path=${encodeURIComponent(path)}">Download</a>`;
    els.exportsGrid.appendChild(row);
  });
}

function buildTransactionRow(row, index) {
  const sourceLabel = getSourceLabel(row.category_source);
  const confidence = getConfidenceMeta(row.category_confidence);
  const confidenceHelp = getConfidenceHelp(row.category_source, row.category_confidence);
  const options = state.categories
    .map((category) => `<option value="${category}" ${category === row.category ? "selected" : ""}>${category}</option>`)
    .join("");
  return `
    <td>${row.date}</td>
    <td>${row.description}</td>
    <td>${row.merchant || ""}</td>
    <td>${Number(row.amount).toFixed(2)}</td>
    <td><select data-index="${index}" class="category-select">${options}</select></td>
    <td><span class="source-chip" title="${confidenceHelp}">${sourceLabel}</span></td>
    <td><span class="confidence-chip ${confidence.tone}" title="${confidenceHelp}">${confidence.label} <small>${confidence.value.toFixed(2)}</small></span></td>
  `;
}

function renderTransactions(rows) {
  state.editedTransactions = rows.map((row) => ({ ...row }));
  els.transactionsTable.innerHTML = "";
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");
    tr.innerHTML = buildTransactionRow(row, index);
    els.transactionsTable.appendChild(tr);
  });

  document.querySelectorAll(".category-select").forEach((select) => {
    select.addEventListener("change", (event) => {
      const index = Number(event.target.dataset.index);
      state.editedTransactions[index].category = event.target.value;
    });
  });
}

function applyCorrectionsToCurrentResult(corrections) {
  if (!state.result) return;
  const correctionMap = new Map(
    corrections.map((row) => [`${row.date}|${row.description}|${Number(row.amount).toFixed(2)}`, row.category]),
  );
  state.result.categorized_transactions = getResultRows().map((row) => {
    const key = `${row.date}|${row.description}|${Number(row.amount).toFixed(2)}`;
    const updatedCategory = correctionMap.get(key);
    if (!updatedCategory) return row;
    return {
      ...row,
      category: updatedCategory,
      category_source: "manual",
      category_confidence: 1.0,
    };
  });
}

function renderAnomalies(items, feedbackRows, anomalyRows) {
  els.anomaliesTable.innerHTML = "";
  state.reviewSelections = new Map();

  if (!items.length) {
    els.anomaliesTable.innerHTML = '<tr><td colspan="8" class="meta">No anomaly review candidates available.</td></tr>';
    return;
  }

  const feedbackMap = new Map(feedbackRows.map((row) => [`${row.date}|${row.description}|${Number(row.amount).toFixed(2)}`, row.feedback]));
  const anomalyMap = new Map(
    anomalyRows.map((row) => [`${row.date}|${row.description}|${Number(row.amount).toFixed(2)}`, row]),
  );

  items.forEach((item) => {
    const key = `${item.date}|${item.description}|${Number(item.amount).toFixed(2)}`;
    const anomaly = anomalyMap.get(key);
    const selected = feedbackMap.get(key) || item.default_feedback || "Skip";
    state.reviewSelections.set(key, selected);
    const tr = document.createElement("tr");
    tr.className = anomaly ? "anomaly-row flagged" : "anomaly-row borderline";
    tr.innerHTML = `
      <td>${item.date}</td>
      <td>${item.description}</td>
      <td>${anomaly?.merchant || ""}</td>
      <td>${Number(item.amount).toFixed(2)}</td>
      <td>${item.category}</td>
      <td>${anomaly ? Number(anomaly.z_score).toFixed(2) : "-"}</td>
      <td><div class="reason-cell"><span class="reason-badge ${anomaly ? "flagged" : "borderline"}">${anomaly ? "Flagged" : "Review"}</span><span>${item.reason}</span></div></td>
      <td>
        <select class="review-select" data-review-key="${key}">
          <option value="Skip">Skip</option>
          <option value="Anomaly">Anomaly</option>
          <option value="Normal">Normal</option>
        </select>
      </td>
    `;
    els.anomaliesTable.appendChild(tr);
  });

  els.anomaliesTable.querySelectorAll(".review-select").forEach((select) => {
    select.value = state.reviewSelections.get(select.dataset.reviewKey) || "Skip";
    select.addEventListener("change", (event) => {
      state.reviewSelections.set(event.target.dataset.reviewKey, event.target.value);
    });
  });
}

function renderTransitions(rows) {
  els.transitionsTable.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.previous_state}</td><td>${row.event}</td><td>${row.next_state}</td>`;
    els.transitionsTable.appendChild(tr);
  });
}

async function renderTrace(logPath) {
  els.traceTable.innerHTML = "";
  const response = await fetch(`/api/download?path=${encodeURIComponent(logPath)}`);
  const text = await response.text();
  text
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((row) => row.event_type === "tool_call" || row.event_type === "tool_result")
    .forEach((row) => {
      const tr = document.createElement("tr");
      const details = JSON.stringify(Object.fromEntries(Object.entries(row.payload || {}).filter(([key]) => key !== "tool")));
      tr.innerHTML = `
        <td>${row.timestamp || ""}</td>
        <td>${row.event_type}</td>
        <td>${row.payload?.tool || ""}</td>
        <td>${details}</td>
      `;
      els.traceTable.appendChild(tr);
    });
}

function setMetrics(result) {
  els.metricState.textContent = result.state;
  els.metricTransactions.textContent = result.metrics.total_transactions;
  els.metricAnomalies.textContent = result.metrics.anomaly_count;
  els.metricSpend.textContent = formatCurrency(result.metrics.total_spend);
}

function showResults() {
  els.snapshotPanel.classList.remove("hidden");
  els.resultsPanel.classList.remove("hidden");
}

function renderOverview(result) {
  const categoryRows = getCategoryRows(result.categorized_transactions || []);
  renderBars(categoryRows);
  renderDonut(categoryRows);
  renderRecurring(result.recurring_expenses || []);
  renderReportChips(result, categoryRows);
  renderActiveFilters();
  els.reportBox.textContent = result.report || "";
}

function applyAnalysisPayload(payload) {
  state.result = payload;
  state.activeCategoryFilter = null;
  state.activeMerchantFilter = null;
  state.categories = payload.category_options || state.categories;

  setMetrics(payload);
  renderOverview(payload);
  renderExports(payload);
  renderFilteredTransactions();
  renderAnomalies(payload.anomaly_review_candidates || [], payload.anomaly_feedback || [], payload.anomalies || []);
  renderTransitions(payload.transitions || []);
  showResults();
}

async function runAnalysis() {
  if (!state.selectedDataset) {
    setStatus("Select or upload a dataset first.", "error");
    return;
  }

  setStatus("Running analysis...", "muted");
  const payload = await api("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset: state.selectedDataset,
      month: els.monthSelect.value,
      seed: Number(els.seedInput.value || 42),
    }),
  });

  applyAnalysisPayload(payload);
  await renderTrace(payload.log_path);
  setStatus(`Analysis complete for ${state.selectedDataset}.`, "success");
}

async function uploadDataset() {
  if (!els.uploadInput.files.length) {
    setStatus("Choose a CSV file first.", "error");
    return;
  }

  const file = els.uploadInput.files[0];
  setStatus("Uploading dataset...", "muted");
  const payload = await api(`/api/upload?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: file,
  });

  await refreshBootstrap(payload.dataset);
  state.selectedDataset = payload.dataset;
  populateSelect(els.datasetSelect, state.datasets, state.selectedDataset);
  populateSelect(els.monthSelect, payload.months || [], "All", true);
  setStatus(`Imported ${payload.row_count} rows into ${payload.dataset}.`, "success");
}

async function saveCorrections() {
  if (!state.result) return;

  const originalMap = new Map(
    getResultRows().map((row) => [`${row.date}|${row.description}|${Number(row.amount).toFixed(2)}`, row.category]),
  );
  const corrections = state.editedTransactions
    .filter((row) => originalMap.get(`${row.date}|${row.description}|${Number(row.amount).toFixed(2)}`) !== row.category)
    .map((row) => ({
      date: row.date,
      description: row.description,
      amount: row.amount,
      category: row.category,
    }));

  if (!corrections.length) {
    setStatus("No category changes to save.", "muted");
    return;
  }

  const payload = await api("/api/corrections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset: state.selectedDataset, corrections }),
  });

  applyCorrectionsToCurrentResult(corrections);
  state.categories = payload.categories || state.categories;
  renderOverview(state.result);
  renderFilteredTransactions();
  setStatus(`Saved ${payload.applied} category corrections. The table is updated now; rerun analysis when you want derived views refreshed.`, "success");
}

async function saveFeedback() {
  if (!state.result) return;

  const rows = [];
  state.reviewSelections.forEach((feedback, key) => {
    if (feedback === "Skip") return;
    const [date, description, amount] = key.split("|");
    rows.push({ date, description, amount: Number(amount), feedback });
  });

  if (!rows.length) {
    setStatus("No anomaly feedback selected.", "muted");
    return;
  }

  const payload = await api("/api/anomaly-feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset: state.selectedDataset, run_id: state.result.run_id, feedback_rows: rows }),
  });

  setStatus(`Saved ${payload.saved} anomaly review decisions.`, "success");
}

function bindTabs() {
  els.tabButtons.forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });
}

function bindControls() {
  els.datasetSelect.addEventListener("change", async (event) => {
    state.selectedDataset = event.target.value;
    state.months = await loadMonths(state.selectedDataset);
    populateSelect(els.monthSelect, state.months, "All", true);
  });

  els.transactionsCategoryFilter.addEventListener("change", (event) => {
    state.activeCategoryFilter = event.target.value === "All" ? null : event.target.value;
    refreshFilteredView(
      state.activeCategoryFilter
        ? `Showing only ${state.activeCategoryFilter} transactions.`
        : "Showing all transactions.",
    );
    if (state.result) {
      renderOverview(state.result);
    }
  });

  els.uploadBtn.addEventListener("click", () => uploadDataset().catch((error) => setStatus(error.message, "error")));
  els.analyzeBtn.addEventListener("click", () => runAnalysis().catch((error) => setStatus(error.message, "error")));
  els.saveCorrectionsBtn.addEventListener("click", () => saveCorrections().catch((error) => setStatus(error.message, "error")));
  els.saveFeedbackBtn.addEventListener("click", () => saveFeedback().catch((error) => setStatus(error.message, "error")));
}

async function init() {
  bindTabs();
  bindControls();
  await refreshBootstrap();
}

init().catch((error) => setStatus(error.message, "error"));

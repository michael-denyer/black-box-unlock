(() => {
  "use strict";

  const payload = JSON.parse(document.getElementById("bbu-report-data").textContent);
  const analysis = payload.analysis;
  const files = analysis.files || [];
  const couplings = payload.couplings || [];
  const filesByPath = new Map(files.map(file => [file.path, file]));
  const couplingIdsByFile = new Map();
  const failedRunsByPath = new Map();
  let selectedPath = null;
  let fileTable;
  let couplingTable;
  let riskChart;
  let mapChart;

  couplings.forEach((pair, index) => {
    [pair.file_a, pair.file_b].forEach(path => {
      if (!couplingIdsByFile.has(path)) couplingIdsByFile.set(path, []);
      couplingIdsByFile.get(path).push(index);
    });
  });
  (analysis.failed_ci_runs || []).forEach(run => {
    (run.implicated_paths || []).forEach(path => {
      if (!failedRunsByPath.has(path)) failedRunsByPath.set(path, []);
      failedRunsByPath.get(path).push(run);
    });
  });

  const formatInteger = value => new Intl.NumberFormat("en-GB").format(value || 0);
  const formatPercent = value => `${((value || 0) * 100).toFixed(1)}%`;
  const text = (tag, value, className) => {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  const clear = node => {
    while (node.firstChild) node.removeChild(node.firstChild);
  };
  const basename = path => path.split("/").filter(Boolean).pop() || path;
  const escapeHtml = value => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

  function couplingSentence(pair) {
    return `${formatInteger(pair.shared_revisions)} shared / min(${formatInteger(pair.revisions_a)}, ${formatInteger(pair.revisions_b)}) revisions · ${formatPercent(pair.raw_ratio)} raw · ${formatPercent(pair.confidence_lower_bound)} lower bound`;
  }

  function addBadge(container, label, tone) {
    container.append(text("span", label, `badge ${tone || ""}`));
  }

  function metric(label, value) {
    const node = text("div", "", "metric");
    node.append(text("strong", value), text("span", label));
    return node;
  }

  function evidenceItem(title, detail) {
    const node = text("div", "", "evidence-item");
    node.append(text("strong", title), text("span", detail));
    return node;
  }

  function selectFile(path, options = {}) {
    const file = filesByPath.get(path);
    if (!file) return;
    selectedPath = path;

    document.getElementById("selected-file-heading").textContent = basename(path);
    document.getElementById("selected-path").textContent = path;

    const badges = document.getElementById("selected-badges");
    clear(badges);
    if (file.is_high_risk) addBadge(badges, "diffuse ownership", "red");
    if (file.build_failures) addBadge(badges, `${file.build_failures} build failures`, "red");
    if (file.bugfix_commits) addBadge(badges, `${file.bugfix_commits} bug-fix revisions`, "amber");
    if (file.xray_failed) addBadge(badges, "X-Ray failed", "red");
    if (!badges.childElementCount) addBadge(badges, "no elevated secondary signal", "green");

    const metrics = document.getElementById("selected-metrics");
    clear(metrics);
    metrics.append(
      metric("revisions", formatInteger(file.commits)),
      metric("complexity", Number(file.complexity || 0).toFixed(1)),
      metric("lines changed", formatInteger(file.lines_changed)),
      metric("hotspot", formatInteger(Math.round(file.hotspot_score || 0))),
    );

    const ownership = document.getElementById("selected-ownership");
    clear(ownership);
    const authorLabel = file.authors.length
      ? `${formatInteger(file.author_count)} authors: ${file.authors.join(", ")}`
      : "No authors were attributed.";
    ownership.append(text("p", authorLabel));
    const failedRuns = failedRunsByPath.get(path) || [];
    const failureLanguage = failedRuns.length
      ? `${failedRuns.length} failed workflow run${failedRuns.length === 1 ? "" : "s"} included this path. This is temporal implication, not proof of causation.`
      : "No collected failed workflow run implicated this path.";
    ownership.append(text("p", failureLanguage, "muted"));

    const pairList = document.getElementById("selected-couplings");
    clear(pairList);
    const pairIds = couplingIdsByFile.get(path) || [];
    pairIds.slice(0, 8).forEach(index => {
      const pair = couplings[index];
      const partner = pair.file_a === path ? pair.file_b : pair.file_a;
      pairList.append(evidenceItem(partner, couplingSentence(pair)));
    });
    if (!pairIds.length) pairList.append(text("p", "No admitted temporal coupling pair.", "empty-state"));
    if (pairIds.length > 8) {
      pairList.append(text("p", `${pairIds.length - 8} more pairs are available in Coupling evidence.`, "muted"));
    }

    const xray = document.getElementById("selected-xray");
    clear(xray);
    const functions = [...(file.functions || [])].sort((a, b) =>
      (b.hotspot_score || 0) - (a.hotspot_score || 0) || a.name.localeCompare(b.name)
    );
    functions.slice(0, 6).forEach(fn => {
      xray.append(evidenceItem(
        fn.name,
        `${formatInteger(fn.revisions)} revisions · complexity ${Number(fn.complexity || 0).toFixed(1)} · hotspot ${formatInteger(Math.round(fn.hotspot_score || 0))}`,
      ));
    });
    if (file.xray_failed) xray.append(text("p", "X-Ray was attempted but failed for this file.", "empty-state"));
    else if (!functions.length) xray.append(text("p", "No function-level evidence was collected.", "empty-state"));

    if (fileTable) {
      const selected = fileTable.getSelectedRows();
      selected.forEach(row => row.getData().path !== path && row.deselect());
      const rows = fileTable.getRows().filter(row => row.getData().path === path);
      if (rows.length === 1 && !rows[0].isSelected()) rows[0].select();
    }
    updateChartSelection(path);
    if (options.focusPanel) document.getElementById("selected-file-heading").focus();
  }

  function updateChartSelection(path) {
    if (riskChart) {
      riskChart.dispatchAction({type: "downplay", seriesIndex: 0});
      const index = files.findIndex(file => file.path === path);
      if (index >= 0) riskChart.dispatchAction({type: "highlight", seriesIndex: 0, dataIndex: index});
    }
    if (mapChart) mapChart.dispatchAction({type: "highlight", seriesId: "repository", name: basename(path)});
  }

  function initializeHeader() {
    document.title = `${analysis.repo} · Black Box Unlock`;
    document.getElementById("side-repo").textContent = analysis.repo;
    document.getElementById("side-window").textContent = `${formatInteger(analysis.analyzed_days)} day window`;
    document.getElementById("report-provenance").textContent =
      `${analysis.repo} · ${formatInteger(analysis.analyzed_days)} days · generated ${new Date(analysis.generated_at).toLocaleString("en-GB", {dateStyle: "medium", timeStyle: "short", timeZone: "UTC"})} UTC`;
    const summary = analysis.summary;
    document.getElementById("stat-files").textContent = formatInteger(summary.total_files);
    document.getElementById("stat-ownership").textContent = formatInteger(summary.high_risk_ownership);
    document.getElementById("stat-couplings").textContent = formatInteger(summary.coupled_pairs);
    document.getElementById("stat-xray").textContent = formatInteger(summary.xrayed_files);
  }

  function strongestConfidence(path) {
    const ids = couplingIdsByFile.get(path) || [];
    return ids.length ? couplings[ids[0]].confidence_lower_bound : 0;
  }

  function initializeFileGrid() {
    const rows = files.map(file => ({
      ...file,
      coupling_count: (couplingIdsByFile.get(file.path) || []).length,
      strongest_confidence: strongestConfidence(file.path),
    }));
    const pathFormatter = cell => text("span", cell.getValue(), "path-cell");
    const inspectFormatter = cell => {
      const button = text("button", "Inspect", "inspect-button");
      button.type = "button";
      button.dataset.path = cell.getRow().getData().path;
      button.addEventListener("click", event => {
        event.stopPropagation();
        selectFile(button.dataset.path, {focusPanel: true});
      });
      return button;
    };
    fileTable = new Tabulator("#file-grid", {
      data: rows,
      index: "path",
      height: "420px",
      layout: "fitDataStretch",
      selectableRows: 1,
      initialSort: [{column: "hotspot_score", dir: "desc"}, {column: "path", dir: "asc"}],
      columns: [
        {title: "File", field: "path", width: 310, minWidth: 220, formatter: pathFormatter},
        {title: "Hotspot", field: "hotspot_score", sorter: "number", hozAlign: "right", formatter: cell => formatInteger(Math.round(cell.getValue()))},
        {title: "Revisions", field: "commits", sorter: "number", hozAlign: "right"},
        {title: "Complexity", field: "complexity", sorter: "number", hozAlign: "right", formatter: cell => Number(cell.getValue()).toFixed(1)},
        {title: "Authors", field: "author_count", sorter: "number", hozAlign: "right"},
        {title: "Bug fixes", field: "bugfix_commits", sorter: "number", hozAlign: "right"},
        {title: "CI", field: "build_failures", sorter: "number", hozAlign: "right"},
        {title: "Best confidence", field: "strongest_confidence", sorter: "number", hozAlign: "right", formatter: cell => formatPercent(cell.getValue())},
        {title: "", field: "path", width: 72, headerSort: false, formatter: inspectFormatter},
      ],
    });
    fileTable.on("rowClick", (_event, row) => selectFile(row.getData().path));
    fileTable.on("dataFiltered", (_filters, visibleRows) => {
      document.getElementById("file-count").textContent = formatInteger(visibleRows.length);
    });
    document.getElementById("file-count").textContent = formatInteger(rows.length);

    const search = document.getElementById("file-search");
    search.addEventListener("input", () => {
      const query = search.value.trim().toLocaleLowerCase();
      if (!query) fileTable.clearFilter();
      else fileTable.setFilter(file =>
        file.path.toLocaleLowerCase().includes(query) ||
        file.authors.some(author => author.toLocaleLowerCase().includes(query))
      );
    });
    search.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        search.value = "";
        search.dispatchEvent(new Event("input"));
      }
    });
  }

  function initializeCouplingGrid() {
    const pathFormatter = cell => text("span", cell.getValue(), "path-cell");
    couplingTable = new Tabulator("#coupling-grid", {
      data: couplings,
      index: "key",
      height: "100%",
      layout: "fitDataStretch",
      initialSort: [
        {column: "confidence_lower_bound", dir: "desc"},
        {column: "shared_revisions", dir: "desc"},
        {column: "raw_ratio", dir: "desc"},
      ],
      columns: [
        {title: "File A", field: "file_a", width: 300, minWidth: 210, formatter: pathFormatter},
        {title: "File B", field: "file_b", width: 300, minWidth: 210, formatter: pathFormatter},
        {title: "95% lower bound", field: "confidence_lower_bound", sorter: "number", hozAlign: "right", formatter: cell => formatPercent(cell.getValue())},
        {title: "Shared", field: "shared_revisions", sorter: "number", hozAlign: "right"},
        {title: "Revisions A", field: "revisions_a", sorter: "number", hozAlign: "right"},
        {title: "Revisions B", field: "revisions_b", sorter: "number", hozAlign: "right"},
        {title: "Denominator", field: "denominator", sorter: "number", hozAlign: "right"},
        {title: "Raw ratio", field: "raw_ratio", sorter: "number", hozAlign: "right", formatter: cell => formatPercent(cell.getValue())},
      ],
    });
    couplingTable.on("rowClick", (_event, row) => {
      selectFile(row.getData().file_a);
      activatePanel("investigation");
    });
    const search = document.getElementById("coupling-search");
    search.addEventListener("input", () => {
      const query = search.value.trim().toLocaleLowerCase();
      if (!query) couplingTable.clearFilter();
      else couplingTable.setFilter(pair =>
        pair.file_a.toLocaleLowerCase().includes(query) ||
        pair.file_b.toLocaleLowerCase().includes(query)
      );
    });
  }

  function riskColour(hotspot, maxHotspot) {
    const ratio = maxHotspot ? hotspot / maxHotspot : 0;
    if (ratio >= .66) return "#b63a30";
    if (ratio >= .33) return "#c77a23";
    return "#28735c";
  }

  function initializeRiskMatrix() {
    const maxLines = Math.max(1, ...files.map(file => file.lines_changed || 0));
    const maxHotspot = Math.max(1, ...files.map(file => file.hotspot_score || 0));
    riskChart = echarts.init(document.getElementById("risk-matrix"), null, {renderer: "canvas"});
    riskChart.setOption({
      animation: false,
      aria: {enabled: true, decal: {show: true}},
      grid: {left: 58, right: 28, top: 28, bottom: 52},
      xAxis: {name: "Revisions", nameLocation: "middle", nameGap: 32, splitLine: {lineStyle: {color: "#e0e0d8"}}},
      yAxis: {name: "Complexity", nameLocation: "middle", nameGap: 42, splitLine: {lineStyle: {color: "#e0e0d8"}}},
      tooltip: {
        trigger: "item",
        formatter: params => {
          const file = filesByPath.get(params.data[3]);
          return `<strong>${escapeHtml(file.path)}</strong><br>${formatInteger(file.commits)} revisions · complexity ${Number(file.complexity).toFixed(1)}<br>${formatInteger(file.lines_changed)} lines changed · hotspot ${formatInteger(Math.round(file.hotspot_score))}`;
        },
      },
      series: [{
        id: "risk",
        type: "scatter",
        data: files.map(file => [file.commits, file.complexity, file.lines_changed, file.path, file.hotspot_score]),
        symbolSize: value => 7 + 20 * Math.sqrt((value[2] || 0) / maxLines),
        itemStyle: {color: params => riskColour(params.data[4], maxHotspot), opacity: .82, borderColor: "#fff", borderWidth: 1},
        emphasis: {scale: 1.3, itemStyle: {borderColor: "#172328", borderWidth: 2}},
      }],
    });
    riskChart.on("click", params => selectFile(params.data[3], {focusPanel: true}));
  }

  function repositoryTree(maxHotspot) {
    const root = {name: analysis.repo, id: "root", children: [], directories: new Map()};
    files.forEach(file => {
      const parts = file.path.split("/").filter(Boolean);
      let node = root;
      let accumulated = "";
      parts.slice(0, -1).forEach(part => {
        accumulated = accumulated ? `${accumulated}/${part}` : part;
        if (!node.directories.has(part)) {
          const directory = {name: part, id: `dir:${accumulated}`, children: [], directories: new Map()};
          node.directories.set(part, directory);
          node.children.push(directory);
        }
        node = node.directories.get(part);
      });
      node.children.push({
        name: parts.at(-1) || file.path,
        id: `file:${file.path}`,
        path: file.path,
        value: Math.max(file.lines_changed || 0, 1),
        actualLinesChanged: file.lines_changed || 0,
        hotspot: file.hotspot_score || 0,
        itemStyle: {color: riskColour(file.hotspot_score || 0, maxHotspot)},
      });
    });
    const stripMaps = node => ({
      ...Object.fromEntries(Object.entries(node).filter(([key]) => key !== "directories")),
      children: (node.children || []).map(stripMaps),
    });
    return stripMaps(root);
  }

  function initializeRepositoryMap() {
    const maxHotspot = Math.max(1, ...files.map(file => file.hotspot_score || 0));
    mapChart = echarts.init(document.getElementById("repository-map"), null, {renderer: "canvas"});
    mapChart.setOption({
      animation: false,
      aria: {enabled: true, decal: {show: true}},
      tooltip: {
        formatter: params => {
          const item = params.data;
          if (!item.path) return escapeHtml(item.name);
          return `<strong>${escapeHtml(item.path)}</strong><br>${formatInteger(item.actualLinesChanged)} lines changed<br>hotspot ${formatInteger(Math.round(item.hotspot))}`;
        },
      },
      series: [{
        id: "repository",
        type: "treemap",
        data: repositoryTree(maxHotspot).children,
        roam: false,
        nodeClick: "zoomToNode",
        breadcrumb: {show: true, bottom: 4},
        label: {show: true, formatter: "{b}"},
        upperLabel: {show: true, height: 24},
        itemStyle: {borderColor: "#fffefa", borderWidth: 2, gapWidth: 1},
        levels: [
          {itemStyle: {borderWidth: 0, gapWidth: 3}},
          {color: ["#315973", "#386f6b", "#7d8860", "#bd752f", "#7a3b39"]},
          {colorSaturation: [.25, .75]},
        ],
      }],
    });
    mapChart.on("click", params => params.data.path && selectFile(params.data.path, {focusPanel: true}));
  }

  function definitionList(entries) {
    const list = document.createElement("dl");
    entries.forEach(([label, value]) => list.append(text("dt", label), text("dd", value)));
    return list;
  }

  function signalRows(items, render) {
    const fragment = document.createDocumentFragment();
    if (!items.length) fragment.append(text("p", "No observations collected.", "empty-state"));
    items.forEach(item => fragment.append(render(item)));
    return fragment;
  }

  function initializeSignals() {
    const ci = document.getElementById("ci-status");
    ci.append(definitionList([
      ["State", analysis.ci_status.state],
      ["Diagnostics", analysis.ci_status.errors.length ? analysis.ci_status.errors.join("; ") : "None"],
    ]));

    const failed = document.getElementById("failed-runs");
    failed.append(signalRows(analysis.failed_ci_runs || [], run => {
      const node = text("div", "", "signal-row");
      node.append(
        text("strong", `${run.workflow_name} · ${run.conclusion.replace("_", " ")}`),
        text("span", `${run.commit_sha.slice(0, 10)} · ${run.implicated_paths.length} implicated paths · ${new Date(run.created_at).toLocaleDateString("en-GB")}`),
        text("span", run.run_url, "mono muted"),
      );
      return node;
    }));

    const flaky = document.getElementById("flaky-steps");
    flaky.append(signalRows(analysis.flaky_steps || [], step => {
      const node = text("div", "", "signal-row");
      node.append(
        text("strong", `${step.job_name} / ${step.step_name}`),
        text("span", `${step.flaky_count} recovered retries · ${step.failures} failures / ${step.total_attempts} attempts`),
        text("span", `${new Date(step.first_seen).toLocaleDateString("en-GB")} – ${new Date(step.last_seen).toLocaleDateString("en-GB")}`, "muted"),
      );
      return node;
    }));

    const policy = analysis.parameters;
    document.getElementById("analysis-policy").append(definitionList([
      ["Analysis window", `${formatInteger(analysis.analyzed_days)} days`],
      ["Coupling threshold", formatPercent(policy.min_coupling)],
      ["Bulk changeset cap", `${formatInteger(policy.max_coupled_files_per_commit)} files`],
      ["Ignored bulk changesets", formatInteger(analysis.summary.ignored_large_changesets)],
      ["X-Ray top files", formatInteger(policy.xray_top)],
      ["CI requested", policy.include_ci ? "Yes" : "No"],
    ]));
  }

  function activatePanel(name, options = {}) {
    document.querySelectorAll(".nav-tab").forEach(button => {
      const active = button.dataset.panel === name;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll(".tab-panel").forEach(panel => {
      panel.hidden = panel.id !== `panel-${name}`;
    });
    if (name === "investigation") {
      requestAnimationFrame(() => {
        riskChart?.resize();
        mapChart?.resize();
        fileTable?.redraw();
      });
    } else if (name === "coupling") requestAnimationFrame(() => couplingTable?.redraw());
    if (options.focusTab) document.querySelector(`[data-panel="${name}"]`).focus();
  }

  function initializeNavigation() {
    const tabs = [...document.querySelectorAll(".nav-tab")];
    tabs.forEach((button, index) => {
      button.addEventListener("click", () => activatePanel(button.dataset.panel));
      button.addEventListener("keydown", event => {
        let target = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") target = tabs[(index + 1) % tabs.length];
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") target = tabs[(index - 1 + tabs.length) % tabs.length];
        if (event.key === "Home") target = tabs[0];
        if (event.key === "End") target = tabs[tabs.length - 1];
        if (target) {
          event.preventDefault();
          activatePanel(target.dataset.panel, {focusTab: true});
        }
      });
    });
    document.querySelectorAll("[data-focus-grid]").forEach(button => button.addEventListener("click", () => {
      document.getElementById("file-search").focus();
      document.getElementById("files-heading").scrollIntoView({block: "start"});
    }));
    document.addEventListener("keydown", event => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        activatePanel("investigation");
        document.getElementById("file-search").focus();
      }
    });
    window.addEventListener("resize", () => {
      riskChart?.resize();
      mapChart?.resize();
    });
  }

  initializeHeader();
  initializeNavigation();
  initializeFileGrid();
  initializeCouplingGrid();
  initializeRiskMatrix();
  initializeRepositoryMap();
  initializeSignals();
  if (files.length) selectFile(files[0].path);
  document.documentElement.dataset.reportReady = "true";
})();

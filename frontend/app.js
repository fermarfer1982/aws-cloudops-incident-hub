const state = {
  incidents: [],
  mode: "demo",
  apiBase: `${window.location.protocol}//${window.location.hostname}:8080`,
};

const labels = {
  critical: "Crítica",
  warning: "Aviso",
  info: "Información",
  open: "Abierto",
  investigating: "Investigando",
  resolved: "Resuelto",
};

const els = {
  mode: document.querySelector("#mode"),
  connection: document.querySelector("#connection"),
  cards: document.querySelector("#cards"),
  table: document.querySelector("#incidentTable"),
  resultCount: document.querySelector("#resultCount"),
  severity: document.querySelector("#severityFilter"),
  status: document.querySelector("#statusFilter"),
  site: document.querySelector("#siteFilter"),
  refresh: document.querySelector("#refreshButton"),
  simulate: document.querySelector("#simulateButton"),
  dialog: document.querySelector("#simulateDialog"),
  closeDialog: document.querySelector("#closeDialog"),
  form: document.querySelector("#simulateForm"),
  feedback: document.querySelector("#formFeedback"),
};

function setConnection(text, cssClass) {
  els.connection.textContent = text;
  els.connection.className = `connection ${cssClass}`;
}

async function loadApiIncidents() {
  const incidents = [];
  let nextToken = null;
  let pageCount = 0;

  do {
    const url = new URL(`${state.apiBase}/events`);
    url.searchParams.set("limit", "100");
    if (nextToken) url.searchParams.set("next_token", nextToken);

    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const page = await response.json();
    incidents.push(...page);
    nextToken = response.headers.get("x-next-token");
    pageCount += 1;
  } while (nextToken && incidents.length < 1000 && pageCount < 20);

  return incidents;
}

async function loadData() {
  try {
    if (state.mode === "demo") {
      const response = await fetch("demo-data.json", { cache: "no-store" });
      state.incidents = await response.json();
      setConnection("Demo activa", "demo");
    } else {
      state.incidents = await loadApiIncidents();
      setConnection("API local conectada", "live");
    }
    renderAll();
  } catch (error) {
    setConnection("API no disponible", "error");
    console.error(error);
  }
}

function getFilteredIncidents() {
  return state.incidents.filter((incident) => {
    return (!els.severity.value || incident.severity === els.severity.value)
      && (!els.status.value || incident.status === els.status.value)
      && (!els.site.value || incident.site === els.site.value);
  });
}

function renderCards() {
  const counts = state.incidents.reduce((acc, item) => {
    acc.total += 1;
    acc[item.severity] += 1;
    if (item.status === "open") acc.open += 1;
    return acc;
  }, { total: 0, critical: 0, warning: 0, info: 0, open: 0 });

  const cards = [
    ["Incidencias totales", counts.total],
    ["Críticas", counts.critical],
    ["Avisos", counts.warning],
    ["Abiertas", counts.open],
  ];
  els.cards.innerHTML = cards.map(([label, value]) => `
    <article class="card"><span>${label}</span><strong>${value}</strong></article>
  `).join("");
}

function renderSiteOptions() {
  const current = els.site.value;
  const sites = [...new Set(state.incidents.map((item) => item.site))].sort();
  els.site.innerHTML = '<option value="">Todas</option>'
    + sites.map((site) => `<option value="${escapeHtml(site)}">${escapeHtml(site)}</option>`).join("");
  els.site.value = sites.includes(current) ? current : "";
}

function renderTable() {
  const incidents = getFilteredIncidents();
  els.resultCount.textContent = `${incidents.length} resultado${incidents.length === 1 ? "" : "s"}`;
  if (!incidents.length) {
    els.table.innerHTML = '<tr><td class="empty" colspan="6">No hay incidencias con estos filtros.</td></tr>';
    return;
  }

  els.table.innerHTML = incidents.map((incident) => `
    <tr>
      <td><span class="badge ${incident.severity}">${labels[incident.severity]}</span></td>
      <td>
        <span class="incident-title">${escapeHtml(incident.message)}</span>
        <span class="incident-type">${escapeHtml(incident.type)} · ${escapeHtml(incident.incident_id)}</span>
      </td>
      <td>${escapeHtml(incident.source)}</td>
      <td>${escapeHtml(incident.site)}</td>
      <td><span class="badge ${incident.status}">${labels[incident.status]}</span></td>
      <td>${new Date(incident.created_at).toLocaleString("es-ES")}</td>
    </tr>
  `).join("");
}

function renderAll() {
  renderCards();
  renderSiteOptions();
  renderTable();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

function classifyDemo(type, value) {
  if (["BACKUP_FAILED", "SERVICE_DOWN", "SITE_OFFLINE", "SECURITY_ALERT"].includes(type)) return "critical";
  if (type === "DISK_USAGE_HIGH" && Number(value) >= 95) return "critical";
  return "warning";
}

els.mode.addEventListener("change", async () => {
  state.mode = els.mode.value;
  await loadData();
});
[els.severity, els.status, els.site].forEach((element) => element.addEventListener("change", renderTable));
els.refresh.addEventListener("click", loadData);
els.simulate.addEventListener("click", () => els.dialog.showModal());
els.closeDialog.addEventListener("click", () => els.dialog.close());

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.feedback.textContent = "Enviando...";
  const data = Object.fromEntries(new FormData(els.form).entries());
  data.value = data.value === "" ? null : Number(data.value);

  try {
    if (state.mode === "local") {
      const response = await fetch(`${state.apiBase}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } else {
      const now = new Date().toISOString();
      state.incidents.unshift({
        ...data,
        incident_id: `DEMO-${Date.now()}`,
        severity: classifyDemo(data.type, data.value),
        status: "open",
        metadata: {},
        created_at: now,
        updated_at: now,
      });
    }
    els.feedback.textContent = "Incidencia registrada correctamente.";
    if (state.mode === "local") await loadData(); else renderAll();
    setTimeout(() => els.dialog.close(), 650);
  } catch (error) {
    els.feedback.textContent = "No se pudo registrar la incidencia.";
    console.error(error);
  }
});

loadData();

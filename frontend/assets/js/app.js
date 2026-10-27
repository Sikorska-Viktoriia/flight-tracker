const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const timeFormat = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" });
const table = document.querySelector("#aircraft-table");
const errorMessage = document.querySelector("#error");
const mapStatus = document.querySelector("#map-status");
const connectionStatus = document.querySelector("#connection-status");
const statusDot = document.querySelector("#status-dot");
const themeToggle = document.querySelector("#theme-toggle");
const searchInput = document.querySelector("#aircraft-search");
const categoryFilter = document.querySelector("#aircraft-category");
const altitudeBand = document.querySelector("#altitude-band");
const altitudeFilter = document.querySelector("#altitude-filter");
const altitudeValue = document.querySelector("#altitude-value");
const emergencyFilter = document.querySelector("#emergency-filter");
const trailsToggle = document.querySelector("#trails-toggle");
const heatmapToggle = document.querySelector("#heatmap-toggle");
const heatmapRange = document.querySelector("#heatmap-range");
const drawer = document.querySelector("#aircraft-drawer");
const timelineSlider = document.querySelector("#timeline-slider");
const playToggle = document.querySelector("#play-toggle");
const playbackSpeed = document.querySelector("#playback-speed");
const playbackTime = document.querySelector("#playback-time");
const chartInterval = document.querySelector("#chart-interval");
const map = L.map("map").setView([51.75, 19], 5);
const aircraftLayer = L.layerGroup().addTo(map);
const trailLayer = L.layerGroup().addTo(map);
const markers = new Map();
const markerData = new Map();
let heatLayer = null;
let heatmapPoints = [];
let chart;
let preferencesError = "";
let historyItems = [];
let timelineSnapshots = [];
let liveSnapshot = null;
let currentSnapshotTime = null;
let selectedAircraftId = null;
let showingPlayback = false;
let playbackTimer = null;
let lastTimelineRefresh = 0;
let lastHeatmapRefresh = 0;
let trailsEnabled = true;
let heatmapEnabled = false;
let sortKey = "callsign";
let sortDirection = 1;

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  className: "dark-tiles",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

function displayNumber(value) {
  return value === null || value === undefined || !Number.isFinite(Number(value))
    ? "—"
    : numberFormat.format(value);
}

function displayTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : timeFormat.format(date);
}

function setMetric(id, value, unit) {
  const element = document.querySelector(`#${id}`);
  element.replaceChildren(document.createTextNode(displayNumber(value)));
  if (unit) {
    const suffix = document.createElement("span");
    suffix.className = "metric-unit";
    suffix.textContent = unit;
    element.append(suffix);
  }
}

function aircraftClass(category) {
  const code = String(category || "").trim().toUpperCase();
  if (code === "A1") return "light";
  if (code === "A2") return "small";
  if (code === "A3" || code === "A4") return "large";
  if (code === "A5") return "heavy";
  if (code === "A6") return "high";
  if (code === "A7") return "rotorcraft";
  return "unknown";
}

function altitudeColor(altitude) {
  if (altitude < 3000) return "#63d6c3";
  if (altitude < 10000) return "#66b9ff";
  return "#f0b65d";
}

function aircraftStatus(plane) {
  if (plane.vertical_rate_mps === null || plane.vertical_rate_mps === undefined) {
    return { label: "Cruising", className: "cruising", icon: "→" };
  }
  if (plane.vertical_rate_mps > 0.5) return { label: "Climbing", className: "climbing", icon: "↑" };
  if (plane.vertical_rate_mps < -0.5) return { label: "Descending", className: "descending", icon: "↓" };
  return { label: "Cruising", className: "cruising", icon: "→" };
}

function aircraftIcon(plane) {
  const rotation = Number.isFinite(plane.heading_deg) ? plane.heading_deg : 0;
  const emergency = ["7500", "7600", "7700"].includes(plane.squawk);
  const color = emergency ? "#ff7474" : altitudeColor(plane.altitude_m);
  return L.divIcon({
    className: "",
    html: `<span class="plane-marker${emergency ? " plane-emergency" : ""}" style="display:block;color:${color};transform:rotate(${rotation}deg)" aria-hidden="true">✈</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });
}

function currentFilters(aircraft) {
  const query = searchInput.value.trim().toLowerCase();
  const selectedClass = categoryFilter.value;
  const minimumAltitude = Number(altitudeFilter.value);
  return aircraft.filter(plane => {
    const searchable = `${plane.callsign} ${plane.icao24} ${plane.aircraft_type}`.toLowerCase();
    if (query && !searchable.includes(query)) return false;
    if (selectedClass !== "all" && aircraftClass(plane.category) !== selectedClass) return false;
    if (altitudeBand.value === "low" && Number(plane.altitude_m) >= 3000) return false;
    if (altitudeBand.value === "high" && Number(plane.altitude_m) <= 10000) return false;
    if (altitudeBand.value === "minimum" && Number(plane.altitude_m) < minimumAltitude) return false;
    if (emergencyFilter.checked && !["7500", "7600", "7700"].includes(plane.squawk)) return false;
    return true;
  });
}

function updateSuggestions(aircraft) {
  const suggestions = document.querySelector("#aircraft-suggestions");
  suggestions.replaceChildren();
  for (const plane of aircraft) {
    for (const value of [plane.callsign, plane.icao24]) {
      if (!value) continue;
      const option = document.createElement("option");
      option.value = value.trim();
      suggestions.append(option);
    }
  }
}

function detailField(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function showAircraftDetails(plane, collectedAt, center = false) {
  selectedAircraftId = plane.icao24;
  drawer.hidden = false;
  detailField("detail-callsign", plane.callsign || plane.icao24 || "Unknown flight");
  detailField(
    "detail-type",
    [plane.aircraft_type, plane.category ? `ADS-B category ${plane.category}` : ""]
      .filter(Boolean).join(" · ") || "Aircraft type unavailable"
  );
  detailField("detail-route", "Origin/destination and schedule are not included in the ADS-B data source.");
  detailField("detail-altitude", `${displayNumber(plane.altitude_m)} m`);
  const status = aircraftStatus(plane);
  const verticalRate = displayNumber(plane.vertical_rate_mps);
  const verticalElement = document.querySelector("#detail-vertical");
  verticalElement.textContent = plane.vertical_rate_mps === null || plane.vertical_rate_mps === undefined
    ? "Unavailable"
    : `${status.icon} ${status.label} · ${verticalRate} m/s`;
  verticalElement.className = `vertical-${status.className}`;
  detailField("detail-speed", `${displayNumber(plane.speed_mps)} m/s`);
  detailField("detail-heading", `${displayNumber(plane.heading_deg)}°`);
  detailField("detail-coordinates", `${Number(plane.latitude).toFixed(4)}, ${Number(plane.longitude).toFixed(4)}`);
  detailField("detail-icao", plane.icao24 || "—");
  const squawkElement = document.querySelector("#detail-squawk");
  const emergencyNames = {
    "7500": "Suspected unlawful interference",
    "7600": "Radio communication failure",
    "7700": "General emergency"
  };
  squawkElement.textContent = plane.squawk
    ? `${plane.squawk}${emergencyNames[plane.squawk] ? ` · ${emergencyNames[plane.squawk]}` : ""}`
    : "—";
  squawkElement.className = ["7500", "7600", "7700"].includes(plane.squawk)
    ? `squawk-emergency squawk-${plane.squawk}`
    : "";
  detailField("detail-time", displayTime(collectedAt));
  if (center) map.setView([plane.latitude, plane.longitude], Math.max(map.getZoom(), 7));
}

function drawTrails(aircraft, collectedAt) {
  trailLayer.clearLayers();
  if (!trailsEnabled) return;
  const cutoff = new Date(collectedAt).getTime() - 15 * 60 * 1000;
  for (const plane of aircraft) {
    const points = [];
    for (const snapshot of timelineSnapshots) {
      const timestamp = new Date(snapshot.collected_at).getTime();
      if (timestamp < cutoff || timestamp > new Date(collectedAt).getTime()) continue;
      const position = snapshot.aircraft.find(item => item.icao24 === plane.icao24);
      if (position) points.push([position.latitude, position.longitude]);
    }
    if (points.length < 2) continue;
    for (let index = 1; index < points.length; index += 1) {
      L.polyline([points[index - 1], points[index]], {
        color: altitudeColor(plane.altitude_m),
        opacity: index / points.length * 0.8,
        weight: 2
      }).addTo(trailLayer);
    }
  }
}

function updateMap(aircraft, collectedAt) {
  const visibleAircraft = currentFilters(aircraft);
  const activeIds = new Set(aircraft.map(plane => plane.icao24));
  const visibleIds = new Set(visibleAircraft.map(plane => plane.icao24));

  for (const plane of visibleAircraft) {
    let marker = markers.get(plane.icao24);
    if (!marker) {
      marker = L.marker([plane.latitude, plane.longitude], {
        icon: aircraftIcon(plane),
        keyboard: true,
        title: plane.callsign || plane.icao24
      });
      marker.on("click", () => {
        const current = markerData.get(plane.icao24);
        if (current) showAircraftDetails(current.plane, current.collectedAt);
      });
      markers.set(plane.icao24, marker);
    } else {
      marker.setLatLng([plane.latitude, plane.longitude]);
      marker.setIcon(aircraftIcon(plane));
    }
    markerData.set(plane.icao24, { plane, collectedAt });
    if (!aircraftLayer.hasLayer(marker)) marker.addTo(aircraftLayer);
    const popup = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = plane.callsign || plane.icao24 || "Unknown flight";
    popup.append(title);
    const details = document.createElement("div");
    details.textContent = [
      plane.aircraft_type || plane.country || "",
      `${displayNumber(plane.altitude_m)} m`,
      `${displayNumber(plane.speed_mps)} m/s`,
      `${displayNumber(plane.heading_deg)}°`
    ].filter(Boolean).join(" · ");
    popup.append(details);
    marker.bindPopup(popup);
  }

  for (const [id, marker] of markers) {
    if (!activeIds.has(id)) {
      aircraftLayer.removeLayer(marker);
      markers.delete(id);
      markerData.delete(id);
    } else if (!visibleIds.has(id)) {
      aircraftLayer.removeLayer(marker);
    }
  }

  drawTrails(visibleAircraft, collectedAt);
  if (heatmapEnabled) {
    if (!heatLayer) heatLayer = L.heatLayer(heatmapPoints, { radius: 24, blur: 18, maxZoom: 8 });
    else heatLayer.setLatLngs(heatmapPoints);
    if (!map.hasLayer(heatLayer)) heatLayer.addTo(map);
    if (map.hasLayer(aircraftLayer)) map.removeLayer(aircraftLayer);
  } else {
    if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
    if (!map.hasLayer(aircraftLayer)) aircraftLayer.addTo(map);
  }

  mapStatus.textContent = `${numberFormat.format(visibleAircraft.length)} of ${numberFormat.format(aircraft.length)} aircraft · ${displayTime(collectedAt)}`;
  if (selectedAircraftId) {
    const selected = aircraft.find(plane => plane.icao24 === selectedAircraftId);
    if (selected && visibleIds.has(selected.icao24)) showAircraftDetails(selected, collectedAt);
    else {
      selectedAircraftId = null;
      drawer.hidden = true;
    }
  }
  updateAircraftTable(visibleAircraft);
}

function updateAircraftTable(aircraft) {
  const sorted = [...aircraft].sort((left, right) => {
    const leftValue = left[sortKey] ?? "";
    const rightValue = right[sortKey] ?? "";
    const comparison = typeof leftValue === "number" && typeof rightValue === "number"
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue));
    return comparison * sortDirection;
  });
  table.replaceChildren();
  if (sorted.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty-cell";
    cell.textContent = "No aircraft match the current filters.";
    row.append(cell);
    table.append(row);
    return;
  }
  for (const plane of sorted) {
    const row = document.createElement("tr");
    row.className = "aircraft-row";
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.setAttribute("aria-label", `Show details for ${plane.callsign || plane.icao24}`);
    const status = aircraftStatus(plane);
    const values = [
      plane.callsign || "—",
      plane.icao24 || "—",
      `${displayNumber(plane.altitude_m)} m`,
      `${displayNumber(plane.speed_mps)} m/s`
    ];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `status-badge ${status.className}`;
    badge.textContent = `${status.icon} ${status.label}`;
    statusCell.append(badge);
    row.append(statusCell);
    const select = () => showAircraftDetails(plane, currentSnapshotTime, true);
    row.addEventListener("click", select);
    row.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select();
      }
    });
    table.append(row);
  }
}

function updateChart(items) {
  const intervalMs = Number(chartInterval.value) * 60 * 1000;
  const since = Date.now() - intervalMs;
  const chronological = items
    .filter(item => new Date(item.collected_at).getTime() >= since)
    .reverse();
  const chartText = document.documentElement.dataset.theme === "light" ? "#526176" : "#91a0b8";
  const chartGrid = document.documentElement.dataset.theme === "light" ? "#d9e1eb" : "#202d42";
  const data = {
    labels: chronological.map(item => new Date(item.collected_at).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit"
    })),
    datasets: [
      {
        label: "Aircraft airborne",
        data: chronological.map(item => item.total_airborne),
        borderColor: "#63d6c3",
        backgroundColor: "rgba(99, 214, 195, .12)",
        fill: true,
        tension: .35,
        pointRadius: 2,
        pointHoverRadius: 5,
        yAxisID: "aircraft"
      },
      {
        label: "Average altitude (m)",
        data: chronological.map(item => item.average_altitude_m),
        borderColor: "#f0b65d",
        backgroundColor: "rgba(240, 182, 93, .08)",
        fill: false,
        tension: .35,
        pointRadius: 2,
        pointHoverRadius: 5,
        yAxisID: "altitude"
      }
    ]
  };
  if (chart) {
    chart.data = data;
    chart.update();
    return;
  }
  chart = new Chart(document.querySelector("#chart"), {
    type: "line",
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: true, labels: { color: chartText, boxWidth: 12 } } },
      scales: {
        x: { grid: { color: chartGrid }, ticks: { color: chartText } },
        aircraft: {
          type: "linear",
          position: "left",
          beginAtZero: true,
          grid: { color: chartGrid },
          ticks: { color: chartText, precision: 0 }
        },
        altitude: {
          type: "linear",
          position: "right",
          beginAtZero: true,
          grid: { drawOnChartArea: false },
          ticks: { color: chartText }
        }
      }
    }
  });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const nextTheme = theme === "dark" ? "light" : "dark";
  themeToggle.textContent = `${nextTheme[0].toUpperCase()}${nextTheme.slice(1)} mode`;
  themeToggle.setAttribute("aria-label", `Switch to ${nextTheme} theme`);
  if (chart) {
    const chartText = theme === "light" ? "#526176" : "#91a0b8";
    const chartGrid = theme === "light" ? "#d9e1eb" : "#202d42";
    for (const scale of Object.values(chart.options.scales)) {
      scale.ticks.color = chartText;
      scale.grid.color = chartGrid;
    }
    chart.options.plugins.legend.labels.color = chartText;
    chart.update();
  }
}

async function loadPreferences() {
  const response = await fetch("/api/session", { cache: "no-store" });
  if (!response.ok) throw new Error(`Session API returned HTTP ${response.status}`);
  const preferences = await response.json();
  applyTheme(preferences.theme);
}

themeToggle.addEventListener("click", async () => {
  const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  try {
    const response = await fetch("/api/session", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme })
    });
    if (!response.ok) throw new Error(`Session API returned HTTP ${response.status}`);
    const preferences = await response.json();
    applyTheme(preferences.theme);
    preferencesError = "";
    errorMessage.textContent = "";
  } catch (error) {
    preferencesError = `Unable to save interface preferences: ${error.message}`;
    errorMessage.textContent = preferencesError;
  }
});

async function fetchTimeline() {
  const response = await fetch("/api/timeline?minutes=60&limit=120", { cache: "no-store" });
  if (!response.ok) throw new Error(`Timeline API returned HTTP ${response.status}`);
  timelineSnapshots = await response.json();
  lastTimelineRefresh = Date.now();
  timelineSlider.max = String(Math.max(0, timelineSnapshots.length - 1));
  timelineSlider.value = timelineSlider.max;
  if (!showingPlayback && timelineSnapshots.length > 0) {
    playbackTime.textContent = `Latest saved position · ${displayTime(timelineSnapshots.at(-1).collected_at)}`;
  } else if (timelineSnapshots.length === 0) {
    playbackTime.textContent = "No saved positions in the last hour";
  }
}

async function fetchHeatmap() {
  const response = await fetch(`/api/heatmap?hours=${heatmapRange.value}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Heatmap API returned HTTP ${response.status}`);
  const points = await response.json();
  heatmapPoints = points.map(point => [point.latitude, point.longitude, point.intensity]);
  lastHeatmapRefresh = Date.now();
}

function renderSnapshot(snapshot, playback = false) {
  currentSnapshotTime = snapshot.collected_at;
  setMetric("total", snapshot.total_airborne);
  setMetric("speed", snapshot.average_speed_mps, "m/s");
  setMetric("altitude", snapshot.max_altitude_m, "m");
  document.querySelector("#callsign").textContent = snapshot.top_flight_callsign || "—";
  document.querySelector("#updated").textContent = `${playback ? "Playback" : "Last snapshot"} · ${displayTime(snapshot.collected_at)}`;
  updateSuggestions(snapshot.aircraft || []);
  updateMap(snapshot.aircraft || [], snapshot.collected_at);
  if (playback) playbackTime.textContent = `Playback · ${displayTime(snapshot.collected_at)}`;
}

function stopPlayback() {
  if (playbackTimer !== null) {
    window.clearTimeout(playbackTimer);
    playbackTimer = null;
  }
  playToggle.textContent = "Play";
  playToggle.setAttribute("aria-pressed", "false");
}

function showTimelineFrame(index) {
  const snapshot = timelineSnapshots[index];
  if (!snapshot) return;
  showingPlayback = true;
  timelineSlider.value = String(index);
  renderSnapshot(snapshot, true);
}

function goLive() {
  stopPlayback();
  showingPlayback = false;
  if (liveSnapshot) renderSnapshot(liveSnapshot);
}

function startPlayback() {
  if (timelineSnapshots.length < 2) {
    playbackTime.textContent = "Not enough saved snapshots to play back";
    return;
  }
  if (Number(timelineSlider.value) >= timelineSnapshots.length - 1) {
    timelineSlider.value = "0";
    showTimelineFrame(0);
  }
  showingPlayback = true;
  playToggle.textContent = "Pause";
  playToggle.setAttribute("aria-pressed", "true");
  schedulePlaybackFrame();
}

function schedulePlaybackFrame() {
  const currentIndex = Number(timelineSlider.value);
  const nextIndex = currentIndex + 1;
  if (nextIndex >= timelineSnapshots.length) {
    stopPlayback();
    return;
  }
  const currentTime = new Date(timelineSnapshots[currentIndex].collected_at).getTime();
  const nextTime = new Date(timelineSnapshots[nextIndex].collected_at).getTime();
  const delay = Math.max(1000, (nextTime - currentTime) / Number(playbackSpeed.value));
  playbackTimer = window.setTimeout(() => {
    showTimelineFrame(nextIndex);
    schedulePlaybackFrame();
  }, delay);
}

async function refresh() {
  try {
    const historyResponse = await fetch("/api/history?limit=500", { cache: "no-store" });
    if (!historyResponse.ok) throw new Error(`History API returned HTTP ${historyResponse.status}`);
    historyItems = await historyResponse.json();
    updateChart(historyItems);

    if (historyItems.length > 0) {
      const latestResponse = await fetch("/api/latest", { cache: "no-store" });
      if (!latestResponse.ok) throw new Error(`Latest API returned HTTP ${latestResponse.status}`);
      liveSnapshot = await latestResponse.json();
      if (!showingPlayback) renderSnapshot(liveSnapshot);
    } else {
      mapStatus.textContent = "Waiting for the first flight snapshot…";
      document.querySelector("#updated").textContent = "Waiting for the first flight snapshot…";
    }

    if (Date.now() - lastTimelineRefresh >= 60000 && !showingPlayback) await fetchTimeline();
    if (heatmapEnabled && Date.now() - lastHeatmapRefresh >= 60000) {
      await fetchHeatmap();
      if (!showingPlayback) renderSnapshot(liveSnapshot);
    }
    errorMessage.textContent = preferencesError;
    connectionStatus.textContent = "Live data connected";
    statusDot.classList.add("online");
  } catch (error) {
    errorMessage.textContent = `Unable to refresh flight data: ${error.message}`;
    connectionStatus.textContent = "Connection issue";
    statusDot.classList.remove("online");
  }
}

searchInput.addEventListener("input", () => liveSnapshot && updateMap(
  showingPlayback
    ? timelineSnapshots[Number(timelineSlider.value)].aircraft
    : liveSnapshot.aircraft,
  showingPlayback
    ? timelineSnapshots[Number(timelineSlider.value)].collected_at
    : liveSnapshot.collected_at
));
categoryFilter.addEventListener("change", () => liveSnapshot && updateMap(
  showingPlayback ? timelineSnapshots[Number(timelineSlider.value)].aircraft : liveSnapshot.aircraft,
  showingPlayback ? timelineSnapshots[Number(timelineSlider.value)].collected_at : liveSnapshot.collected_at
));
altitudeFilter.addEventListener("input", () => {
  altitudeValue.textContent = `${altitudeFilter.value} m`;
  categoryFilter.dispatchEvent(new Event("change"));
});
altitudeBand.addEventListener("change", () => {
  altitudeFilter.disabled = altitudeBand.value !== "minimum";
  categoryFilter.dispatchEvent(new Event("change"));
});
emergencyFilter.addEventListener("change", () => categoryFilter.dispatchEvent(new Event("change")));

trailsToggle.addEventListener("click", () => {
  trailsEnabled = !trailsEnabled;
  trailsToggle.textContent = trailsEnabled ? "Trails on" : "Trails off";
  trailsToggle.setAttribute("aria-pressed", String(trailsEnabled));
  categoryFilter.dispatchEvent(new Event("change"));
});

heatmapToggle.addEventListener("click", async () => {
  const enable = !heatmapEnabled;
  if (enable && typeof L.heatLayer !== "function") {
    errorMessage.textContent = "Traffic heatmap library failed to load. Check your internet connection and retry.";
    return;
  }
  try {
    if (enable) await fetchHeatmap();
    heatmapEnabled = enable;
    heatmapToggle.setAttribute("aria-pressed", String(heatmapEnabled));
    heatmapToggle.textContent = heatmapEnabled ? "Aircraft positions" : "Traffic heatmap";
    categoryFilter.dispatchEvent(new Event("change"));
    errorMessage.textContent = preferencesError;
  } catch (error) {
    errorMessage.textContent = `Unable to load traffic heatmap: ${error.message}`;
  }
});

heatmapRange.addEventListener("change", async () => {
  if (!heatmapEnabled) return;
  try {
    await fetchHeatmap();
    categoryFilter.dispatchEvent(new Event("change"));
    errorMessage.textContent = preferencesError;
  } catch (error) {
    errorMessage.textContent = `Unable to load traffic heatmap: ${error.message}`;
  }
});

document.querySelector("#drawer-close").addEventListener("click", () => {
  drawer.hidden = true;
  selectedAircraftId = null;
});

document.querySelectorAll(".sort-button").forEach(button => {
  button.addEventListener("click", () => {
    const nextKey = button.dataset.sort;
    sortDirection = sortKey === nextKey ? -sortDirection : 1;
    sortKey = nextKey;
    categoryFilter.dispatchEvent(new Event("change"));
  });
});

chartInterval.addEventListener("change", () => updateChart(historyItems));
playToggle.addEventListener("click", () => {
  if (playbackTimer === null) startPlayback();
  else stopPlayback();
});
playbackSpeed.addEventListener("change", () => {
  if (playbackTimer !== null) {
    stopPlayback();
    startPlayback();
  }
});
timelineSlider.addEventListener("input", () => {
  stopPlayback();
  showTimelineFrame(Number(timelineSlider.value));
});
document.querySelector("#live-toggle").addEventListener("click", goLive);

loadPreferences()
  .catch(error => {
    preferencesError = `Unable to load interface preferences: ${error.message}`;
    errorMessage.textContent = preferencesError;
  })
  .finally(async () => {
    try {
      await fetchTimeline();
    } catch (error) {
      preferencesError = `Unable to load playback history: ${error.message}`;
      errorMessage.textContent = preferencesError;
    }
    await refresh();
  });
window.setInterval(refresh, 15000);

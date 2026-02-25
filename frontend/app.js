const GATEWAY_IP = "127.0.0.1";   // laptop-only
const WS_URL = `ws://${GATEWAY_IP}:8000/ws`;
const API_BASE = `http://${GATEWAY_IP}:8000/api`;

const statusEl = document.getElementById("status");
const odEls = [
  document.getElementById("od1"),
  document.getElementById("od2"),
  document.getElementById("od3"),
  document.getElementById("od4"),
];
const odTimeEl = document.getElementById("odTime");

const pidTableBody = document.getElementById("pidTable");

const dateFromEl = document.getElementById("dateFrom");
const dateToEl = document.getElementById("dateTo");
const timeFromEl = document.getElementById("timeFrom");
const timeToEl = document.getElementById("timeTo");

let ws;
let pid = {
  setpoints: [0.65,0.60,0.60,0.60],
  kp: [10,8,8,8],
  ki: [1.2,0.8,0.8,0.8],
  kd: [0,0,0,0],
};

function isoTime(epochSec){ return new Date(epochSec*1000).toISOString(); }
function shortTime(epochSec){ return new Date(epochSec*1000).toLocaleTimeString(); }

function renderPidTable() {
  pidTableBody.innerHTML = "";
  for (let ch=0; ch<4; ch++) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${ch+1}</td>
      <td><input type="number" step="0.001" id="sp${ch}" value="${pid.setpoints[ch]}"></td>
      <td><input type="number" step="0.01" id="kp${ch}" value="${pid.kp[ch]}"></td>
      <td><input type="number" step="0.01" id="ki${ch}" value="${pid.ki[ch]}"></td>
      <td><input type="number" step="0.01" id="kd${ch}" value="${pid.kd[ch]}"></td>
    `;
    pidTableBody.appendChild(tr);
  }
}

function collectPidFromInputs() {
  const out = { setpoints: [], kp: [], ki: [], kd: [] };
  for (let ch=0; ch<4; ch++) {
    out.setpoints.push(parseFloat(document.getElementById(`sp${ch}`).value));
    out.kp.push(parseFloat(document.getElementById(`kp${ch}`).value));
    out.ki.push(parseFloat(document.getElementById(`ki${ch}`).value));
    out.kd.push(parseFloat(document.getElementById(`kd${ch}`).value));
  }
  return out;
}

async function loadPidFromServer() {
  const res = await fetch(`${API_BASE}/pid`);
  pid = await res.json();
  renderPidTable();
}

async function applyPidToServer() {
  const payload = collectPidFromInputs();
  await fetch(`${API_BASE}/pid`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

// Chart.js
const ctx = document.getElementById("odChart").getContext("2d");
const chartData = {
  labels: [],
  datasets: [
    { label: "OD CH1", data: [] },
    { label: "OD CH2", data: [] },
    { label: "OD CH3", data: [] },
    { label: "OD CH4", data: [] },
  ]
};

const chart = new Chart(ctx, {
  type: "line",
  data: chartData,
  options: {
    animation: false,
    responsive: true,
    scales: {
      x: { title: { display: true, text: "Time" } },
      y: { title: { display: true, text: "OD" } }
    }
  }
});

function addPoint(epochSec, odArr) {
  chartData.labels.push(shortTime(epochSec));
  for (let i=0; i<4; i++) {
    chartData.datasets[i].data.push(odArr[i]);
  }
  if (chartData.labels.length > 240) {
    chartData.labels.shift();
    for (let i=0; i<4; i++) chartData.datasets[i].data.shift();
  }
  chart.update();
}

function connectWS() {
  statusEl.textContent = `Connecting…`;
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    statusEl.textContent = "Connected • receiving data";
  };

  ws.onmessage = (evt) => {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }

    if (msg.type === "status") {
      statusEl.textContent = `Status: ${msg.status}`;
    }

    if (msg.type === "pid" && msg.pid) {
      pid = msg.pid;
      renderPidTable();
    }

    if (msg.type === "od") {
      const ts = msg.ts;
      const od = msg.od;

      for (let i=0; i<4; i++) {
        odEls[i].textContent = Number(od[i]).toFixed(3);
      }
      odTimeEl.textContent = isoTime(ts);
      addPoint(ts, od);
    }
  };

  ws.onclose = () => {
    statusEl.textContent = "Disconnected • reconnecting…";
    setTimeout(connectWS, 1500);
  };

  ws.onerror = () => {
    statusEl.textContent = "WebSocket error";
  };
}

function downloadCSVFromServer() {
  const df = (dateFromEl.value || "").trim();
  const dt = (dateToEl.value || "").trim();
  const tf = (timeFromEl.value || "00:00").trim();
  const tt = (timeToEl.value || "23:59").trim();

  if (!df || !dt) return;

  const url = `${API_BASE}/log.csv?date_from=${encodeURIComponent(df)}&date_to=${encodeURIComponent(dt)}&time_from=${encodeURIComponent(tf)}&time_to=${encodeURIComponent(tt)}`;
  window.location.href = url;
}

document.getElementById("applyPid").addEventListener("click", applyPidToServer);
document.getElementById("downloadCsv").addEventListener("click", downloadCSVFromServer);

// Defaults (today)
(function setDefaultDates(){
  const now = new Date();
  const dd = String(now.getDate()).padStart(2,"0");
  const mm = String(now.getMonth()+1).padStart(2,"0");
  const yyyy = now.getFullYear();
  const today = `${dd}.${mm}.${yyyy}`;
  if (!dateFromEl.value) dateFromEl.value = today;
  if (!dateToEl.value) dateToEl.value = today;
  if (!timeFromEl.value) timeFromEl.value = "00:00";
  if (!timeToEl.value) timeToEl.value = "23:59";
})();

renderPidTable();
loadPidFromServer().catch(()=>{});
connectWS();

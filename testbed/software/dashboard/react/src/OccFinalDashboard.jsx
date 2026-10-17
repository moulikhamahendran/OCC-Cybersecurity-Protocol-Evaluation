
import { useEffect, useState } from "react";
import research from "./occ-research-data.json";
import "./OccFinalDashboard.css";

const ROOT = (import.meta.env.VITE_API_BASE || window.location.origin).replace(/\/$/, "");

const protocols = [
  { id: "mqtt", name: "MQTT", endpoint: "/api/v1/mqtt/live/vehicles",
    profiles: ["Plain", "Credentials", "TLS + credentials"] },
  { id: "opcua", name: "OPC UA", endpoint: "/api/v1/opcua/live",
    profiles: ["None", "Sign", "Sign & Encrypt"] },
  { id: "dds", name: "DDS", endpoint: "/api/v1/dds/live",
    profiles: ["Baseline", "Participant signing", "Participant encryption"] }
];

const tabs = [
  ["live", "Live Monitoring — C2"],
  ["nine", "Nine-Mode Evaluation"],
  ["network", "Network Architecture"]
];

const text = (value, unit = "") => {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "number" && Number.isFinite(value))
    return `${Number(value.toFixed(3))}${unit}`;
  return String(value);
};

const mode = v => String(v?.security_profile || "UNKNOWN").toUpperCase();

function vehiclesOf(response) {
  const records = response?.vehicles;
  if (Array.isArray(records)) return records;
  if (records && typeof records === "object") return Object.values(records);
  return [];
}

function Telemetry({ vehicle }) {
  const t = vehicle?.telemetry || {};
  const data = [
    ["Vehicle", vehicle?.vehicle_id],
    ["Sequence", vehicle?.seq ?? vehicle?.sequence],
    ["Speed", t.speed],
    ["Battery", t.battery_pct ?? t.battery, "%"],
    ["Position X", t.pos_x],
    ["Position Y", t.pos_y],
    ["Heading", t.heading, "°"],
    ["State", t.state]
  ];
  return <dl className="occf-metrics">
    {data.map(([name, value, unit]) =>
      <div key={name}><dt>{name}</dt><dd>{text(value, unit || "")}</dd></div>
    )}
  </dl>;
}


const PALETTE = {
  mqtt: "#38bdf8",
  opcua: "#a78bfa",
  dds: "#34d399"
};

function TrendChart({values, color, label}) {
  const samples = values.filter(v => typeof v === "number" && Number.isFinite(v));
  if (samples.length < 2) {
    return <div className="occf-chart-empty">
      Waiting for fresh C2 samples
    </div>;
  }
  const w = 420, h = 112, pad = 8;
  const lo = Math.min(...samples);
  const hi = Math.max(...samples);
  const range = hi - lo || 1;
  const points = samples.map((v, i) => {
    const x = pad + i * (w-2*pad) / Math.max(1,samples.length-1);
    const y = h-pad - (v-lo)*(h-2*pad)/range;
    return `${x},${y}`;
  }).join(" ");
  return <div className="occf-chart">
    <div className="occf-chart-label">
      <span>{label}</span>
      <span>{text(samples[samples.length-1])}</span>
    </div>
    <svg viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none" role="img"
      aria-label={`Recent ${label} telemetry`}>
      <polyline points={points} fill="none"
        stroke={color} strokeWidth="3"
        strokeLinejoin="round" strokeLinecap="round"/>
    </svg>
  </div>;
}

function PerformanceBars({records, metricKey, title, unit}) {
  const values = protocols.map(p => {
    const row = records[p.id];
    const n = row?.[metricKey] == null ? NaN : Number(row[metricKey]);
    return {p, value:Number.isFinite(n)?n:null};
  });
  const max = Math.max(1, ...values.map(x => x.value || 0));
  return <div className="occf-performance-chart">
    <h3>{title}</h3>
    {values.map(({p,value}) =>
      <div className="occf-bar-row" key={p.id}>
        <span>{p.name}</span>
        <div className="occf-bar-track">
          {value !== null &&
            <div className="occf-bar-fill"
              style={{
                width:`${100*value/max}%`,
                background:PALETTE[p.id]
              }}/>}
        </div>
        <strong>{value === null ? "N/A" : text(value,unit)}</strong>
      </div>
    )}
  </div>;
}

function RichTopology({live}) {
  return <section className="occf-topology">
    <div className="occf-top-row">
      <div className="occf-top-node">
        <b>VM-001 / VM-002</b>
        <small>ESP32 vehicle telemetry</small>
      </div>
      <div className="occf-top-node attacker">
        <b>VM-003</b>
        <small>Attack experiments</small>
      </div>
    </div>
    <div className="occf-top-arrow">↓</div>
    <div className="occf-protocol-routes">
      {protocols.map(p => {
        const online = vehiclesOf(live?.[p.id]?.data)
          .some(v => v.online === true);
        return <div className="occf-route" key={p.id}
          style={{"--route":PALETTE[p.id]}}>
          <b>{p.name}</b>
          <small>{p.id === "mqtt" ? "Broker" :
            p.id === "opcua" ? "OPC UA server" : "XRCE agent"}</small>
          <span>{online ? "RECEIVER FRESH" : "STALE / OFFLINE"}</span>
        </div>;
      })}
    </div>
    <div className="occf-top-arrow">↓</div>
    <div className="occf-top-node">
      <b>Mac Gateway</b>
      <small>Protocol forwarding · WireGuard connectivity</small>
    </div>
    <div className="occf-top-arrow">↓</div>
    <div className="occf-top-node pi">
      <b>Raspberry Pi 5 — OCC</b>
      <small>MQTT / OPC UA / DDS receivers · validation · FastAPI</small>
    </div>
    <div className="occf-top-arrow">↓</div>
    <div className="occf-top-node pi">
      <b>Cybersecurity Dashboard</b>
      <small>Live monitoring · KPIs · recorded security evidence</small>
    </div>
    <p className="occf-note">
      Receiver freshness does not independently verify transport encryption.
      The attacker is a separate testbed participant, not part of the
      normal vehicle telemetry route.
    </p>
  </section>;
}

function LiveMonitoring({ live, history }) {
  return <div className="occf-stack">
    <div className="occf-intro">
      <h2>C2 — Live Vehicle Monitoring</h2>
      <p>Real telemetry from OCC receivers. A card is LIVE only when the receiver
        reports fresh C2 observations. C0 and C1 data are never relabelled as C2.</p>
    </div>
    <div className="occf-three">
      {protocols.map(p => {
        const response = live[p.id];
        const vehicles = vehiclesOf(response?.data);
        const v = vehicles.find(x => x.online === true && mode(x) === "C2");
        const unknown = vehicles.some(x => x.online === true && mode(x) === "UNKNOWN");
        return <article className="occf-card" key={p.id}>
          <div className="occf-card-head">
            <h3>{p.name} — C2</h3>
            <span className={"occf-status " + (v ? "occf-on" : "")}>
              {response?.error ? "API ERROR" : v ? "LIVE" : "NOT ACTIVE"}
            </span>
          </div>
          <p className="occf-subtitle">{p.profiles[2]}</p>
          {v ? <Telemetry vehicle={v}/> :
            <div className="occf-empty">
              No verified fresh C2 telemetry.
              {unknown && <p>The receiver has live data, but its security
                profile is UNKNOWN; it cannot be classified as C2.</p>}
            </div>}
          {v && <div className="occf-live-charts">
            <TrendChart
              values={(history?.[p.id] || []).map(x => x.speed)}
              color={PALETTE[p.id]} label="Speed"/>
            <TrendChart
              values={(history?.[p.id] || []).map(x => x.battery)}
              color={PALETTE[p.id]} label="Battery (%)"/>
          </div>}
          {v && <p className="occf-note">
            Receiver age: {text(v.source_age_seconds ?? v.age_seconds, " s")}
          </p>}
        </article>;
      })}
    </div>
    <p className="occf-note">DDS participant security does not independently
      establish encryption of the ESP32-to-XRCE-agent UDP uplink.</p>
  </div>;
}

function recordedRows(p) {
  return research?.performance?.[p.id] || [];
}

function rowsForMode(p, profile) {
  return recordedRows(p).filter(r =>
    String(r.security_level || r.security_profile || "").toUpperCase() === profile
  );
}

function representative(p, profile) {
  const rows = rowsForMode(p, profile);
  const preferred = p.id === "dds" ? "NET-ideal" : "NET-proxy-ideal";
  return rows.find(r => (r.net_profile || r.network_profile) === preferred) ||
         rows.find(r => ["NET-ideal", "NET-proxy-ideal"].includes(
           r.net_profile || r.network_profile
         )) || rows[0] || null;
}

function metric(r, names) {
  for (const key of names) {
    if (r?.[key] !== undefined && r?.[key] !== null && r?.[key] !== "")
      return text(r[key]);
  }
  return "Not recorded";
}

function NineModes() {
  const [selected, setSelected] = useState(["mqtt", "C0"]);
  const p = protocols.find(x => x.id === selected[0]);
  const level = selected[1];
  const row = representative(p, level);
  const hardware = (research?.performance?.hardware || []).filter(r =>
    String(r.protocol || "").toLowerCase().replace(/[\s_-]/g, "") === p.id &&
    String(r.security_profile || r.security_level || "").toUpperCase() === level
  );

  return <div className="occf-stack">
    <div className="occf-intro">
      <h2>Nine-Mode Protocol Evaluation</h2>
      <p>Select any configuration to view one representative recorded
        result. These are historical experiments, not current live telemetry.</p>
    </div>
    <div className="occf-matrix">
      {protocols.map(protocol =>
        <div className="occf-matrix-row" key={protocol.id}>
          <strong>{protocol.name}</strong>
          {["C0", "C1", "C2"].map((profile, i) =>
            <button key={profile}
              type="button"
              aria-pressed={selected[0] === protocol.id && level === profile}
              className={selected[0] === protocol.id && level === profile ? "selected" : ""}
              onClick={() => setSelected([protocol.id, profile])}>
              <b>{profile}</b><small>{protocol.profiles[i]}</small>
            </button>
          )}
        </div>
      )}
    </div>

    <article className="occf-card">
      <div className="occf-card-head">
        <h3>{p.name} / {level}</h3>
        <span className="occf-status">RECORDED</span>
      </div>
      <p className="occf-subtitle">{p.profiles[Number(level[1])]}</p>
      <div className="occf-security-explanation">
        <strong>Security configuration</strong>
        <p>{p.id === "mqtt"
          ? (level === "C0" ? "Plain MQTT transport" :
             level === "C1" ? "Broker credentials over unencrypted transport" :
             "TLS transport with broker credentials")
          : p.id === "opcua"
          ? (level === "C0" ? "No OPC UA message security" :
             level === "C1" ? "Basic256Sha256 with message signing" :
             "Basic256Sha256 with signing and encryption")
          : (level === "C0" ? "Baseline DDS operation" :
             level === "C1" ? "DDS participant-level signing" :
             "DDS participant-level encryption")}</p>
        <small>Protocol security configurations are not directly
          interchangeable. Hardware verification and research KPIs
          have different evidence scopes.</small>
      </div>
      <p className="occf-note">
        Representative software/network experiment.
        Hardware telemetry values are not substituted for software KPIs.
      </p>
      <dl className="occf-metrics">
        <div><dt>Network condition</dt><dd>{row ? text(row.net_profile || row.network_profile) : "Not recorded"}</dd></div>
        <div><dt>Latency (ms)</dt><dd>{metric(row, ["latency_mean_ms"])}</dd></div>
        <div><dt>Jitter (ms)</dt><dd>{metric(row, ["jitter_mean_ms"])}</dd></div>
        <div><dt>Throughput (msg/s)</dt><dd>{metric(row, [
          "throughput_mean_messages_per_second",
          "throughput_mean_msg_s", "throughput_mean_mps"
        ])}</dd></div>
        <div><dt>Application loss (%)</dt><dd>{metric(row, [
          "application_delivery_loss_mean_percent",
          "loss_mean_percent"
        ])}</dd></div>
        <div><dt>Experiment runs</dt><dd>{metric(row, ["runs"])}</dd></div>
        <div><dt>Hardware pilot entries</dt><dd>{hardware.length ? hardware.length : "Not in bundle"}</dd></div>
      </dl>
      <p className="occf-note">
        Software KPI measurements and physical hardware acceptance evidence
        have different measurement scopes and must not be conflated.
      </p>
    </article>
  </div>;
}

function EvidenceTable({ title, rows }) {
  if (!Array.isArray(rows) || rows.length === 0)
    return <section className="occf-card">
      <h3>{title}</h3><p className="occf-empty">No records in the bundled dataset.</p>
    </section>;

  const columns = [...new Set(rows.slice(0, 20).flatMap(r =>
    r && typeof r === "object" ? Object.keys(r) : []
  ))].slice(0, 12);

  return <section className="occf-card">
    <h3>{title} <span className="occf-count">{rows.length} records</span></h3>
    <div className="occf-tablewrap"><table>
      <thead><tr>{columns.map(k => <th key={k}>{k.replace(/_/g, " ")}</th>)}</tr></thead>
      <tbody>{rows.slice(0, 100).map((row, i) =>
        <tr key={i}>{columns.map(k => <td key={k}>
          {typeof row[k] === "object" ? JSON.stringify(row[k]) : text(row[k])}
        </td>)}</tr>
      )}</tbody>
    </table></div>
    {rows.length > 100 && <p className="occf-note">First 100 records shown.</p>}
  </section>;
}

function Performance() {
  const [security, setSecurity] = useState("C2");
  const [network, setNetwork] = useState("Baseline");
  const selectedRecords = Object.fromEntries(protocols.map(p => {
    const candidates = rowsForMode(p,security);
    const actualProfile = network === "Baseline"
      ? (p.id === "dds" ? "NET-ideal" : "NET-proxy-ideal")
      : network;
    const candidate = candidates.find(r =>
      (r.net_profile || r.network_profile) === actualProfile);
    return [p.id, candidate || null];
  }));
  const graphRecords = Object.fromEntries(protocols.map(p => {
    const r = selectedRecords[p.id];
    return [p.id, {
      latency:r?.latency_mean_ms == null ? NaN : Number(r.latency_mean_ms),
      jitter:r?.jitter_mean_ms == null ? NaN : Number(r.jitter_mean_ms),
      throughput:(r?.throughput_mean_messages_per_second ??
        r?.throughput_mean_msg_s ?? r?.throughput_mean_mps) == null
          ? NaN : Number(r.throughput_mean_messages_per_second ??
            r.throughput_mean_msg_s ?? r.throughput_mean_mps),
      loss:(r?.application_delivery_loss_mean_percent ??
        r?.loss_mean_percent) == null ? NaN :
          Number(r.application_delivery_loss_mean_percent ??
            r.loss_mean_percent)
    }];
  }));
  return <div className="occf-stack">
    <div className="occf-performance-controls">
      <label>Security level
        <select value={security} onChange={e=>setSecurity(e.target.value)}>
          {["C0","C1","C2"].map(v=><option key={v}>{v}</option>)}
        </select>
      </label>
      <label>Network profile
        <select value={network} onChange={e=>setNetwork(e.target.value)}>
          {[
            ["Baseline", "Ideal / Baseline"],
            ["NET-delay", "Delay"],
            ["NET-jitter", "Jitter"],
            ["NET-loss", "Loss"]
          ].map(([value,label]) =>
            <option key={value} value={value}>{label}</option>
          )}
        </select>
      </label>
    </div>
    <div className="occf-four">
      <PerformanceBars records={graphRecords}
        metricKey="latency" title="Mean latency" unit=" ms"/>
      <PerformanceBars records={graphRecords}
        metricKey="jitter" title="Mean jitter" unit=" ms"/>
      <PerformanceBars records={graphRecords}
        metricKey="throughput" title="Throughput" unit=" msg/s"/>
      <PerformanceBars records={graphRecords}
        metricKey="loss" title="Application loss" unit=" %"/>
    </div>
    <p className="occf-note">Missing data is shown as N/A.
      For Ideal / Baseline, MQTT and OPC UA use
      NET-proxy-ideal; DDS uses NET-ideal. These baseline
      conditions are not strictly equivalent. Original experimental
      records remain unchanged.</p>
    <div className="occf-intro">
      <h2>Performance Analysis</h2>
      <p>Historical software/network experimental results. Protocol
        scheduling, QoS and measurement boundaries may differ.</p>
    </div>
    {protocols.map(p =>
      <EvidenceTable key={p.id} title={p.name + " performance results"}
        rows={recordedRows(p)}/>
    )}
    <EvidenceTable title="Physical hardware pilot results"
      rows={research?.performance?.hardware || []}/>
  </div>;
}

function Security() {
  const s = research?.security || {};
  const sections = [
    ["MQTT attack experiments", s.mqtt],
    ["OPC UA security experiments", s.opcua],
    ["DDS DoS experiments", s.dds_dos],
    ["DDS participant controls", s.dds_controls]
  ];
  return <div className="occf-stack">
    <div className="occf-intro">
      <h2>Cybersecurity Analysis</h2>
      <p>Recorded observations only. A completed experiment does not
        automatically imply an attack was prevented.</p>
    </div>
    {sections.map(([label, rows]) =>
      <EvidenceTable key={label} title={label} rows={rows || []}/>
    )}
  </div>;
}

function Network({live}) {
  return <div className="occf-stack">
    <div className="occf-intro">
      <h2>Network Architecture</h2>
      <p>Operational telemetry and cybersecurity testbed architecture.</p>
    </div>
    <RichTopology live={live}/>
    <details className="occf-card">
      <summary>Simple architecture overview</summary>
      <section className="occf-architecture">
      <div className="occf-node"><b>ESP32 Vehicles</b>
        <span>VM-001 / VM-002 · VM-003 attacker</span></div>
      <div className="occf-arrow">↓</div>
      <div className="occf-node"><b>Communication Protocols</b>
        <span>MQTT · OPC UA · Micro XRCE-DDS</span></div>
      <div className="occf-arrow">↓</div>
      <div className="occf-node"><b>Mac Gateway / VPN Connectivity</b>
        <span>Network forwarding and secure remote connectivity</span></div>
      <div className="occf-arrow">↓</div>
      <div className="occf-node"><b>Raspberry Pi 5 — OCC</b>
        <span>Protocol receivers · validation · telemetry observers · FastAPI</span></div>
      <div className="occf-arrow">↓</div>
      <div className="occf-node"><b>OCC Dashboard</b>
        <span>Live observations · research evidence · attack outcomes</span></div>
      </section>
    </details>
  </div>;
}

export default function OccFinalDashboard() {
  const [tab, setTab] = useState("live");
  const [live, setLive] = useState({});
  const [updated, setUpdated] = useState("—");
  const [history, setHistory] = useState({});

  useEffect(() => {
    let mounted = true;
    let busy = false;

    async function refresh() {
      if (busy) return;
      busy = true;
      try {
        const entries = await Promise.all(protocols.map(async p => {
          try {
            const response = await fetch(ROOT + p.endpoint, {cache:"no-store"});
            if (!response.ok) throw Error(`HTTP ${response.status}`);
            return [p.id, {data:await response.json(), error:null}];
          } catch (error) {
            return [p.id, {data:null, error:String(error)}];
          }
        }));
        if (mounted) {
          setLive(Object.fromEntries(entries));
          setHistory(previous => {
            const next = {...previous};
            for (const [protocol, packet] of entries) {
              const v = vehiclesOf(packet.data)
                .find(x => x.online === true && mode(x) === "C2");
              if (!v) continue;
              const seq = v.seq ?? v.sequence;
              if (seq == null) continue;
              const key = protocol;
              const arr = next[key] || [];
              if (arr.length && arr[arr.length-1].seq === seq) continue;
              const t = v.telemetry || {};
              next[key] = [...arr, {
                seq,
                speed: Number(t.speed),
                battery: Number(t.battery_pct ?? t.battery)
              }].slice(-90);
            }
            return next;
          });
          setUpdated(new Date().toLocaleTimeString());
        }
      } finally { busy = false; }
    }

    refresh();
    const timer = setInterval(refresh, 2500);
    return () => {mounted = false; clearInterval(timer);};
  }, []);

  return <div className="occf-shell">
    <header className="occf-header">
      <div>
        <p className="occf-eyebrow">CYBER-PHYSICAL SYSTEMS · RESEARCH TESTBED</p>
        <h1>OCC Cybersecurity Platform</h1>
        <p>ESP32 vehicles · MQTT · OPC UA · DDS · Raspberry Pi 5</p>
      </div>
      <div className="occf-updated">Last API refresh: {updated}</div>
    </header>
    <nav className="occf-tabs" aria-label="OCC dashboard sections">
      {tabs.map(([key, name]) =>
        <button type="button" key={key}
          className={tab === key ? "active" : ""}
          aria-current={tab === key ? "page" : undefined}
          onClick={() => setTab(key)}>{name}</button>
      )}
    </nav>
    <main className="occf-main">
      {tab === "live" && <LiveMonitoring live={live} history={history}/>}
      {tab === "nine" && <NineModes/>}
      {tab === "network" && <Network live={live}/>}
    </main>
    <footer className="occf-footer">
      Operational telemetry and historical research evidence are shown separately.
      No simulated measurements.
    </footer>
  </div>;
}

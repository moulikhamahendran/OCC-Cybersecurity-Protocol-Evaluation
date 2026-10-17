
import { useEffect, useState } from "react";
import "./occ-simple-dashboard.css";
import NineModeMatrix from "./NineModeEvidenceMatrix.jsx";
import researchBundle from "./occ-research-data.json";

const API = (import.meta.env.VITE_API_BASE || window.location.origin).replace(/\/$/, "");
const protocols = [
  { key: "mqtt", name: "MQTT", path: "/api/v1/mqtt/live/vehicles", color: "#38bdf8",
    subtitle: "Lightweight publish / subscribe",
    route: "ESP32 → Mosquitto Broker → OCC",
    security: "C0 Plain · C1 Credentials · C2 TLS",
    details: "MQTT transports vehicle telemetry over TCP through a broker. OCC receives subscribed telemetry messages." },
  { key: "opcua", name: "OPC UA", path: "/api/v1/opcua/live", color: "#c4b5fd",
    subtitle: "Industrial client / server",
    route: "ESP32 Client → OPC UA Server → OCC",
    security: "C0 None · C1 Sign · C2 Sign & Encrypt",
    details: "OPC UA provides industrial information exchange through secured client/server communication and structured telemetry." },
  { key: "dds", name: "DDS", path: "/api/v1/dds/live", color: "#6ee7b7",
    subtitle: "Data-centric publish / subscribe",
    route: "ESP32 → XRCE Agent → DDS Subscriber",
    security: "C0 Baseline · C1/C2 DDS profiles",
    details: "Micro XRCE-DDS connects the ESP32 to the agent. DDS security on the participant side does not itself prove encryption of the XRCE uplink." }
];

const fmt = (x, unit = "") => {
  if (x === undefined || x === null || x === "") return "—";
  return typeof x === "number" && Number.isFinite(x)
    ? `${Number(x.toFixed(2))}${unit}` : `${x}${unit}`;
};

const num = x => {
  const n = Number(x);
  return x === "" || x == null || !Number.isFinite(n) ? null : n;
};

const pick = (data, p, id) =>
  (data?.vehicles || []).find(v =>
    v.vehicle_id === id &&
    String(v.protocol || "").toLowerCase() === p.key
  );

function Spark({ values, color }) {
  if (!values || values.length < 2) return <p className="muted">Collecting browser-session samples…</p>;
  const w = 440, h = 92, pad = 6;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) =>
    `${pad + i * (w - 2 * pad) / Math.max(1, values.length - 1)},${h - pad - (v - min) * (h - 2 * pad) / span}`
  ).join(" ");
  return <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
    role="img" aria-label="Recent browser-session telemetry trend">
    <polyline points={points} fill="none" stroke={color} strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function ProtocolCard({ p, v, error }) {
  const online = v?.online === true && !error;
  const t = online ? (v.telemetry || {}) : {};
  const battery = num(t.battery_pct ?? t.battery);
  const age = v?.source_age_seconds ?? v?.age_seconds;
  return <article className="protocol-card" style={{"--protocol": p.color}}>
    <div className="card-top"><h2>{p.name}</h2>
      <span className={`status ${online ? "online" : "offline"}`}>
        {error ? "API ERROR" : online ? "LIVE" : "OFFLINE / STALE"}
      </span>
    </div>
    <div className="info-banner">
      <b>{p.subtitle}</b><p>{p.route}</p><small>{p.security}</small>
      <details><summary>How this protocol works</summary><p>{p.details}</p></details>
    </div>
    <p className="profile">Vehicle: {v?.vehicle_id || "—"} · Security: {online ? fmt(v?.security_profile) : "—"}</p>
    <div className="metrics">
      <Metric label="Sequence" value={online ? fmt(v?.seq ?? v?.sequence) : "—"} />
      <Metric label="Speed" value={online ? fmt(t.speed) : "—"} />
      <Metric label="Battery" value={online ? fmt(battery, "%") : "—"} />
      <Metric label="Position X" value={online ? fmt(t.pos_x) : "—"} />
      <Metric label="Position Y" value={online ? fmt(t.pos_y) : "—"} />
      <Metric label="Heading" value={online ? fmt(t.heading, "°") : "—"} />
      <Metric label="Vehicle state" value={online ? fmt(t.state) : "—"} />
      <Metric label="Data age" value={online ? fmt(age, " s") : "—"} />
    </div>
    <div className="battery-track" aria-label="Reported vehicle battery level">
      <div style={{width: `${online && battery != null ? Math.max(0, Math.min(100, battery)) : 0}%`,
        background: p.color}} />
    </div>
    <p className="foot">{online ? "Fresh receiver observations" : "No verified fresh receiver observation"}</p>
  </article>;
}

function LiveView({ states, history, vehicle }) {
  return <>

    <div className="cards">{protocols.map(p =>
      <ProtocolCard key={p.key} p={p} v={states[p.key]} error={states[p.key + "_error"]} />
    )}</div>
    <section className="panel">
      <div className="section-heading"><h2>Live vehicle trends</h2>
        <span className="muted">Browser-session samples · Not benchmark KPIs</span></div>
      <div className="trends">{protocols.map(p => {
        const samples = history[p.key] || [];
        return <div className="trend" key={p.key}>
          <h3 style={{color: p.color}}>{p.name}</h3>
          <p>Speed</p><Spark values={samples.map(s => s.speed).filter(x => x != null)} color={p.color} />
          <p>Battery (%)</p><Spark values={samples.map(s => s.battery).filter(x => x != null)} color={p.color} />
          <small>{samples.length} valid snapshots retained for {vehicle}</small>
        </div>;
      })}</div>
    </section>
  </>;
}


function NetworkView({ states }) {
  const online = p =>
    states[p.key]?.online === true &&
    !states[p.key + "_error"];

  const active = protocols.filter(online).length;

  const vehicle =
    states.mqtt?.vehicle_id ||
    states.opcua?.vehicle_id ||
    states.dds?.vehicle_id ||
    "VM-001";

  const routes = {
    mqtt: "Mosquitto broker → OCC receiver",
    opcua: "OPC UA server → OCC receiver",
    dds: "Micro XRCE-DDS agent → DDS subscriber"
  };

  return <section className="panel occ-topology">
    <style>{`
      .occ-topology {
        padding: 24px;
      }
      .occ-topology .top-head {
        display:flex; justify-content:space-between;
        gap:15px; align-items:center; flex-wrap:wrap;
        margin-bottom:24px;
      }
      .occ-topology .top-heading {
        font-size:23px; font-weight:800;
        color:#f1f5f9; margin:0;
      }
      .occ-topology .top-sub {
        color:#94a3b8; font-size:12px; margin-top:5px;
      }
      .occ-topology .top-count {
        background:#103f39; color:#6ee7b7;
        border:1px solid #176455;
        border-radius:30px; padding:8px 13px;
        font-size:12px; font-weight:700;
      }
      .occ-topology .top-node {
        background:linear-gradient(145deg,#1b324d,#16283f);
        border:1px solid #365673;
        border-radius:13px; padding:17px 22px;
        text-align:center;
      }
      .occ-topology .top-node strong {
        display:block; color:#f1f5f9;
        font-size:15px; margin-bottom:5px;
      }
      .occ-topology .top-node span {
        font-size:12px; color:#b4c7da;
      }
      .occ-topology .source-node {
        max-width:350px; margin:0 auto;
      }
      .occ-topology .occ-arrow {
        text-align:center; font-size:24px;
        color:#64b7eb; padding:8px;
      }
      .occ-topology .backhaul {
        display:grid; grid-template-columns:1fr auto 1fr;
        align-items:center; gap:15px;
        max-width:850px; margin:auto;
      }
      .occ-topology .backhaul-arrow {
        font-size:23px; color:#64b7eb;
      }
      .occ-topology .section-title {
        text-align:center; color:#b7cce1;
        font-size:12px; letter-spacing:1.5px;
        text-transform:uppercase;
        margin:20px 0 14px;
      }
      .occ-topology .protocol-grid {
        display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
        gap:12px;
      }
      .occ-topology .protocol-node {
        min-width:0; background:#102037;
        border:1px solid #36506d;
        border-top:3px solid var(--protocol);
        border-radius:12px; padding:16px;
      }
      .occ-topology .protocol-head {
        display:flex; justify-content:space-between;
        gap:8px; align-items:center;
      }
      .occ-topology .protocol-head strong {
        font-size:16px; color:var(--protocol);
      }
      .occ-topology .health-pill {
        font-size:10px; font-weight:700;
        border-radius:20px; padding:5px 8px;
        background:#3d2935; color:#fca5a5;
      }
      .occ-topology .health-pill.ok {
        background:#12423c; color:#6ee7b7;
      }
      .occ-topology .protocol-route {
        color:#afc0d6; font-size:11px;
        line-height:1.5; min-height:36px;
        margin:12px 0;
      }
      .occ-topology .protocol-data {
        display:grid; grid-template-columns:1fr 1fr;
        gap:11px; border-top:1px solid #31445d;
        padding-top:13px;
      }
      .occ-topology .protocol-data span {
        color:#94a3b8; font-size:10px; display:block;
      }
      .occ-topology .protocol-data b {
        color:#e2edfc; font-size:12px;
        display:block; margin-top:4px;
        overflow-wrap:anywhere;
      }
      .occ-topology .bottom-node {
        max-width:500px; margin:auto;
      }
      .occ-topology .legend-row {
        display:grid; grid-template-columns:repeat(3,1fr);
        gap:10px; margin-top:22px;
      }
      .occ-topology .legend-box {
        background:#14253d; border:1px solid #30445d;
        border-radius:9px; padding:13px;
      }
      .occ-topology .legend-box b {
        display:block; font-size:12px; color:#e5effe;
      }
      .occ-topology .legend-box p {
        font-size:11px; line-height:1.5;
        color:#a8bad0; margin:7px 0 0;
      }
      .occ-topology .top-note {
        margin-top:17px; padding:13px;
        border:1px solid #535038;
        border-radius:8px; color:#f4ca71;
        background:#202b35; font-size:11px;
        line-height:1.6;
      }
      @media(max-width:760px) {
        .occ-topology .protocol-grid,
        .occ-topology .legend-row {
          grid-template-columns:1fr;
        }
        .occ-topology .backhaul {
          grid-template-columns:1fr;
        }
        .occ-topology .backhaul-arrow {
          transform:rotate(90deg);
          text-align:center;
        }
      }
    `}</style>

    <div className="top-head">
      <div>
        <h2 className="top-heading">OCC Network Architecture</h2>
        <p className="top-sub">
          End-to-end vehicle communication and receiver monitoring
        </p>
      </div>
      <span className="top-count">
        ● {active}/3 protocols fresh
      </span>
    </div>

    <div className="top-node source-node">
      <strong>ESP32 Vehicle · {vehicle}</strong>
      <span>Vehicle telemetry · Wi-Fi transport</span>
    </div>

    <div className="occ-arrow">↓</div>

    <div className="backhaul">
      <div className="top-node">
        <strong>Local Mac Gateway</strong>
        <span>192.168.1.114 · Protocol relays</span>
      </div>
      <div className="backhaul-arrow">→</div>
      <div className="top-node">
        <strong>WireGuard VPN</strong>
        <span>Mac-to-Pi routed backhaul</span>
      </div>
    </div>

    <div className="occ-arrow">↓</div>

    <div className="section-title">Protocol receiver paths</div>

    <div className="protocol-grid">
      {protocols.map(p => {
        const v = states[p.key];
        const ok = online(p);
        const t = ok ? v.telemetry || {} : {};
        const age = v?.source_age_seconds ??
                    v?.age_seconds ??
                    v?.observer_state_age_seconds;

        return <article
          key={p.key}
          className="protocol-node"
          style={{"--protocol":p.color}}
        >
          <div className="protocol-head">
            <strong>{p.name}</strong>
            <span className={"health-pill" + (ok ? " ok" : "")}>
              {ok ? "● FRESH" : "● STALE"}
            </span>
          </div>

          <p className="protocol-route">
            {routes[p.key]}
          </p>

          <div className="protocol-data">
            <div>
              <span>Security profile</span>
              <b>{ok ? v.security_profile || "UNKNOWN" : "—"}</b>
            </div>
            <div>
              <span>Sequence</span>
              <b>{ok ? v.seq ?? v.sequence ?? "—" : "—"}</b>
            </div>
            <div>
              <span>Vehicle speed</span>
              <b>{ok ? fmt(t.speed) : "—"}</b>
            </div>
            <div>
              <span>Battery</span>
              <b>{ok ? fmt(t.battery_pct ?? t.battery,"%") : "—"}</b>
            </div>
            <div>
              <span>Data age</span>
              <b>{ok ? fmt(age," s") : "—"}</b>
            </div>
            <div>
              <span>Vehicle state</span>
              <b>{ok ? t.state || "—" : "—"}</b>
            </div>
          </div>
        </article>;
      })}
    </div>

    <div className="occ-arrow">↓</div>

    <div className="top-node bottom-node">
      <strong>Raspberry Pi 5 — OCC</strong>
      <span>
        10.8.0.3 · Telemetry receivers · Validation · FastAPI · Dashboard
      </span>
    </div>

    <div className="legend-row">
      <div className="legend-box">
        <b>Communication</b>
        <p>
          MQTT broker, OPC UA server, and DDS subscriber
          provide distinct telemetry transport paths.
        </p>
      </div>
      <div className="legend-box">
        <b>Security monitoring</b>
        <p>
          C0/C1/C2 are protocol profiles. The live profile
          is displayed only when reported by its receiver.
        </p>
      </div>
      <div className="legend-box">
        <b>OCC observation</b>
        <p>
          Freshness and vehicle fields are obtained from
          current receiver API responses.
        </p>
      </div>
    </div>

    <div className="top-note">
      The gateway addresses represent the configured testbed
      architecture, not an automatically discovered network map.
      Fresh telemetry does not prove end-to-end encryption,
      authenticated XRCE uplink, or continuous availability.
      DDS UNKNOWN remains unclassified.
    </div>
  </section>;
}

function DataTable({ rows, columns, empty = "No matching recorded data" }) {
  if (!rows?.length) return <p className="muted">{empty}</p>;
  return <div className="table-scroll"><table>
    <thead><tr>{columns.map(c => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}>{columns.map(([field]) =>
      <td key={field}>{field.startsWith("_") ? (r[field] ?? "—") :
        num(r[field]) !== null && !["security_level", "repeat"].includes(field)
          ? fmt(num(r[field])) : (r[field] ?? "—")}</td>
    )}</tr>)}</tbody>
  </table></div>;
}

function PerformanceView({ research }) {
  const [profile, setProfile] = useState("C0");
  const [network, setNetwork] = useState("NET-ideal");
  if (!research) return <section className="panel"><p className="muted">Research bundle unavailable. Historical values are not fabricated.</p></section>;
  const perf = research.performance || {};
  const metrics = [
    ["MQTT", perf.mqtt || [], "network_profile",
      "latency_mean_ms", "jitter_mean_ms", "throughput_mean_messages_per_second", "application_delivery_loss_mean_percent"],
    ["OPC UA", perf.opcua || [], "net_profile",
      "latency_mean_ms", "jitter_mean_ms", "throughput_mean_msg_s", null],
    ["DDS", perf.dds || [], "net_profile",
      "latency_mean_ms", "jitter_mean_ms", "throughput_mean_mps", "loss_mean_percent"]
  ];
  const rows = metrics.map(([name, data, nk, lk, jk, tk, loss]) => {
    const r = data.find(x => x.security_level === profile && x[nk] === network);
    return {
      name, latency: r ? fmt(num(r[lk])) : "—",
      jitter: r ? fmt(num(r[jk])) : "—",
      throughput: r ? fmt(num(r[tk])) : "—",
      loss: r && loss ? fmt(num(r[loss])) : "Not supplied",
      runs: r?.runs || "—"
    };
  });
  return <div className="stack">
    <section className="panel">
      <div className="section-heading"><h2>Historical protocol KPIs</h2><span className="tag">Recorded experiments</span></div>
      <div className="filters">
        <label>Security <select value={profile} onChange={e => setProfile(e.target.value)}>
          {["C0","C1","C2"].map(x => <option key={x}>{x}</option>)}
        </select></label>
        <label>Network <select value={network} onChange={e => setNetwork(e.target.value)}>
          {["NET-ideal","NET-proxy-ideal","NET-delay","NET-jitter","NET-loss"].map(x => <option key={x}>{x}</option>)}
        </select></label>
      </div>
      <DataTable rows={rows} columns={[
        ["name","Protocol"],["latency","Latency (ms)"],["jitter","Jitter (ms)"],
        ["throughput","Throughput (msg/s)"],["loss","Reported loss (%)"],["runs","Runs"]
      ]}/>
      <p className="notice">These values come from separate software/network datasets. Different measurement boundaries may apply; they are not an experimentally controlled ranking of protocol speed.</p>
    </section>
    <section className="panel">
      <h2>Hardware cross-protocol pilot</h2>
      <DataTable rows={(perf.hardware || []).map(x => ({
        ...x, _protocol: x.protocol, _profile: x.security_profile
      }))} columns={[
        ["_protocol","Protocol"],["_profile","Security"],["timing_metric","Timing metric"],
        ["timing_scope","Scope"],["mean_timing_ms","Mean timing (ms)"],
        ["mean_throughput_msg_s","Messages/s"],["mean_loss_percent","Loss (%)"]
      ]}/>
      <p className="notice">Timing metrics and scopes are preserved exactly as recorded. ACK round-trip time must not be equated with one-way transport latency.</p>
    </section>
  </div>;
}

function SecurityView({ research }) {
  if (!research) return <section className="panel"><p className="muted">Historical security data unavailable.</p></section>;
  const sec = research.security || {};
  const attacks = (sec.mqtt || []);
  const groups = {};
  for (const r of attacks) {
    const id = `${r.security_level} / ${r.attack}`;
    groups[id] ||= {profile:r.security_level, attack:r.attack, runs:0, detected:0, blocked:0, flagged:0};
    groups[id].runs++;
    groups[id].detected += Number(r.detected || 0);
    groups[id].blocked += Number(r.block_events || 0);
    groups[id].flagged += Number(r.flag_events || 0);
  }
  return <div className="stack">
    <section className="panel"><div className="section-heading">
      <h2>MQTT attack experiments</h2><span className="tag">Historical · Not live alerts</span>
    </div>
      <DataTable rows={Object.values(groups)} columns={[
        ["profile","Security"],["attack","Attack"],["runs","Runs"],
        ["detected","Detected runs"],["blocked","Block events"],["flagged","Flag events"]
      ]}/>
    </section>
    <section className="panel"><h2>OPC UA security controls</h2>
      <DataTable rows={sec.opcua || []} columns={[
        ["security_level","Security"],["attack_type","Control"],
        ["runs","Runs"],["controls_passed","Passed"],["observed_outcome","Observed"]
      ]}/>
    </section>
    <section className="panel"><h2>DDS DoS availability impact</h2>
      <DataTable rows={sec.dds_dos || []} columns={[
        ["security_level","Security"],["runs","Runs"],
        ["legitimate_loss_percent_mean","Mean loss (%)"],
        ["latency_ms_mean","Latency (ms)"],
        ["impacted_runs","Impacted runs"]
      ]}/>
      <p className="notice">Attack model: compromised authorized publisher flooding. A recorded experiment PASS does not mean that availability was protected.</p>
    </section>
    <section className="panel"><h2>DDS participant security controls</h2>
      <DataTable rows={sec.dds_controls || []} columns={[
        ["control_id","Control"],["description","Description"],
        ["verdict","Recorded verdict"],["evidence","Evidence"]
      ]}/>
      <p className="notice">Participant-level security tests do not independently verify ESP32-to-XRCE-agent transport encryption.</p>
    </section>
  </div>;
}

export default function App() {
  const [tab, setTab] = useState("live");
  const [vehicle, setVehicle] = useState("VM-001");
  const [results, setResults] = useState({});
  const [research] = useState(researchBundle);
  const [history, setHistory] = useState({});
  const [updated, setUpdated] = useState("—");


  useEffect(() => {
    setHistory({});
    let active = true;
    let busy = false;
    async function update() {
      if (busy) return;
      busy = true;
      try {
        const entries = await Promise.all(protocols.map(async p => {
          try {
            const r = await fetch(API + p.path, {cache:"no-store"});
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return [p.key, {data: await r.json(), error:null}];
          } catch (e) { return [p.key, {data:null,error:String(e)}]; }
        }));
        if (!active) return;
        const next = Object.fromEntries(entries);
        setResults(next);
        setUpdated(new Date().toLocaleTimeString());
        setHistory(previous => {
          const result = {...previous};
          for (const p of protocols) {
            const v = pick(next[p.key]?.data, p, vehicle);
            if (v?.online !== true) continue;
            const t = v.telemetry || {};
            const speed = num(t.speed), battery = num(t.battery_pct ?? t.battery);
            const seq = v.seq ?? v.sequence;
            if ((speed === null && battery === null) || seq == null) continue;
            const arr = result[p.key] || [];
            if (arr.length && arr[arr.length-1].seq === seq) continue;
            result[p.key] = [...arr, {seq, speed, battery}].slice(-120);
          }
          return result;
        });
      } finally {busy = false;}
    }
    update();
    const id = setInterval(update, 2500);
    return () => {active = false; clearInterval(id);};
  }, [vehicle]);

  const states = {};
  for (const p of protocols) {
    states[p.key] = pick(results[p.key]?.data, p, vehicle);
    states[p.key + "_error"] = results[p.key]?.error;
  }
  const liveCount = protocols.filter(p => states[p.key]?.online === true && !states[p.key + "_error"]).length;

  function exportCSV() {
    const header = ["protocol","vehicle","seq","speed","battery_pct","pos_x","pos_y","heading","state","age_seconds"];
    const rows = protocols.map(p => {
      const v = states[p.key], t = v?.online ? (v.telemetry || {}) : {};
      return [p.name, vehicle,v?.seq ?? "",t.speed ?? "",
        t.battery_pct ?? t.battery ?? "",t.pos_x ?? "",t.pos_y ?? "",
        t.heading ?? "",t.state ?? "",v?.source_age_seconds ?? v?.age_seconds ?? ""];
    });
    const esc = x => `"${String(x ?? "").replaceAll('"','""')}"`;
    const text = [header,...rows].map(r => r.map(esc).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([text],{type:"text/csv"}));
    const a = document.createElement("a"); a.href=url; a.download="occ_live_snapshot.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  return <div className="page">
    <header className="dashboard-header">
      <div><div className="eyebrow">OPERATION CONTROL CENTER · CYBERSECURITY TESTBED</div>
        <h1>OCC Cybersecurity Control Center</h1>
        <p>Raspberry Pi 5 · ESP32 · MQTT / OPC UA / DDS</p></div>
      <div className="header-controls">
        <span className="system-chip">{liveCount}/3 protocols fresh</span>
        <label>Vehicle <select value={vehicle} onChange={e=>setVehicle(e.target.value)}>
          <option>VM-001</option><option>VM-002</option>
        </select></label>
        <small>Updated: {updated}</small>
      </div>
    </header>
    <nav className="tabbar" aria-label="Dashboard views">
      {[
        ["live","Live Monitoring"],["hardware","Nine-Mode Hardware"],["network","Network Topology"],

      ].map(([id,name]) => <button key={id} className={tab===id?"active":""}
        onClick={()=>setTab(id)}>{name}</button>)}
    </nav>
    <div className="toolbar">
      <span>Live receiver observations and separately labelled recorded research evidence</span>
      <div className="toolbar-buttons">
        <button onClick={exportCSV}>Export snapshot CSV</button>
        <button onClick={()=>document.documentElement.requestFullscreen?.()}>Fullscreen</button>
      </div>
    </div>
    <main>
      {tab==="live" && <LiveView states={states} history={history} vehicle={vehicle}/>}
      {tab==="hardware" && <NineModeMatrix states={states}/>}
      {tab==="network" && <NetworkView states={states}/>}


    </main>
    <footer>Only fresh received observations are labelled live. Historical experiments are not live attack activity. Security claims require verified configuration and transport evidence.</footer>
  </div>;
}

import { useEffect, useState } from "react";

const PROTOCOLS = ["mqtt", "opcua", "dds"];
const PROFILES = ["C0", "C1", "C2"];
const ROOT = (import.meta.env.VITE_API_BASE || window.location.origin).replace(/\/$/, "");
function DdsLivePanel() {
  const [live, setLive] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const response = await fetch(`${ROOT}/api/v1/dds/live`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (active) {
          setLive(data);
          setError("");
        }
      } catch {
        if (active) {
          setLive(null);
          setError("DDS API unavailable");
        }
      }
    }
    refresh();
    const timer = setInterval(refresh, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const vehicle = live?.vehicles?.[0];
  const online = vehicle?.online === true;

  return (
    <section style={{
      border: "1px solid #77889966",
      padding: 16,
      borderRadius: 10,
      marginBottom: 18
    }}>
      <h3>DDS Live OCC Receiver</h3>
      <p>Status: <strong>{
        error || (online ? "ONLINE" : "OFFLINE / STALE")
      }</strong></p>
      <p>
        Vehicle: {vehicle?.vehicle_id || "Unavailable"} ·
        Sequence: {vehicle?.seq ?? "—"} ·
        Profile: {vehicle?.security_profile || "UNKNOWN"}
      </p>
      <p>
        Telemetry availability: {
          vehicle?.telemetry_availability || "Unavailable"
        } · Source age: {
          vehicle?.source_age_seconds ?? "—"
        } seconds
      </p>
      {online && vehicle?.telemetry && (
        <pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>
          {JSON.stringify(vehicle.telemetry,null,2)}
        </pre>
      )}
      <small>
        DDS operational observations, not benchmark measurements
        or cryptographic security verification.
      </small>
    </section>
  );
}

export default function KpiMatrix() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [protocol, setProtocol] = useState("all");
  useEffect(() => {
    let live = true;
    fetch(`${ROOT}/api/v1/evaluation/summary`)
      .then(async r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(v => { if (live) setData(v); })
      .catch(e => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, []);
  const datasets = (data?.datasets || []).filter(d => protocol === "all" || d.protocol === protocol);
  return <section id="occ-evaluation-matrix" style={{margin:"22px auto",padding:20,maxWidth:1180,border:"1px solid #77889966",borderRadius:12,fontFamily:"inherit"}}>
    <DdsLivePanel />
      <h2>Cross-protocol security and KPI evidence</h2>
    <p>MQTT · OPC UA · DDS — C0 / C1 / C2. Historical results, separate from live telemetry.</p>
    {error && <p role="alert">Evaluation endpoint not available yet: {error}</p>}
    {!data && !error && <p>Loading recorded experiments…</p>}
    {data && <>
      <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"center"}}>
        <thead><tr><th>Protocol</th>{PROFILES.map(c=><th key={c}>{c}</th>)}</tr></thead>
        <tbody>{PROTOCOLS.map(p=><tr key={p}><th style={{textTransform:"uppercase"}}>{p}</th>{PROFILES.map(c=>{
          const x = data.matrix?.[p]?.[c] || {};
          return <td key={c} style={{padding:12,borderTop:"1px solid #77889944"}}>{x.datasets ? `${x.datasets} dataset(s)` : "No categorized summary"}</td>;
        })}</tr>)}</tbody>
      </table></div>
      <p style={{fontSize:12,opacity:.8}}>Dataset presence does not mean hardware end-to-end verification or proven security enforcement.</p>
      <label htmlFor="occ-matrix-filter">Dataset filter: </label>
      <select id="occ-matrix-filter" value={protocol} onChange={e=>setProtocol(e.target.value)}>
        <option value="all">All protocols</option>{PROTOCOLS.map(p=><option value={p} key={p}>{p.toUpperCase()}</option>)}
      </select>
      <p>{datasets.length} summary files indexed</p>
      <div style={{maxHeight:280,overflow:"auto"}}>{datasets.map(d=><details key={d.path} style={{borderTop:"1px solid #77889944",padding:"8px 0"}}>
        <summary style={{cursor:"pointer",overflowWrap:"anywhere"}}>{d.protocol.toUpperCase()} — {d.path}</summary>
        <p>Profiles detected: {d.profiles_found?.join(", ") || "Not identified"} · Rows scanned: {d.row_count_scanned ?? "Unavailable"} · Context: {d.condition_hint}</p>
        <p style={{fontSize:12}}>Fields: {d.columns?.join(", ") || "Unavailable"}</p>
      </details>)}</div>
    </>}
  </section>;
}

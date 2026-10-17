import React, { useEffect, useState } from "react";

const modes = ["MQTT", "OPCUA"];
const profiles = ["C0", "C1", "C2"];

export default function OccUnifiedSwitchPanel() {
  const [vehicles, setVehicles] = useState([]);
  const [operatorToken, setOperatorToken] = useState("");
  const [protocol, setProtocol] = useState("OPCUA");
  const [profile, setProfile] = useState("C1");
  const [target, setTarget] = useState("VM-001");
  const [state, setState] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/v1/vehicles", { cache: "no-store" });
        if (!response.ok) return;
        const data = await response.json();
        if (alive) setVehicles((data.vehicles || []).filter(v => v.vehicle_id !== "VM-003"));
      } catch { /* connection retry on next refresh */ }
    };
    refresh();
    const timer = setInterval(refresh, 2500);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch(`/api/v1/management/vehicles/${encodeURIComponent(target)}/status`, { cache: "no-store" });
        if (!response.ok) return;
        const json = await response.json();
        if (active) { setState(json); if (["verified", "timeout"].includes(json.phase)) setBusy(false); }
      } catch { /* leave visible state unchanged */ }
    };
    refresh();
    const timer = setInterval(refresh, 1200);
    return () => { active = false; clearInterval(timer); };
  }, [target]);

  const selected = vehicles.find(v => v.vehicle_id === target);
  const activeSwitch = ["queued", "device_confirmed"].includes(state?.phase);
  const switchNow = async () => {
    if (!operatorToken || !selected?.online || busy || activeSwitch) return;
    setBusy(true);
    setMessage("Submitting authenticated request; mode is not verified yet.");
    try {
      const response = await fetch(`/api/v1/management/vehicles/${encodeURIComponent(target)}/switch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-OCC-Operator-Token": operatorToken },
        body: JSON.stringify({ protocol, profile }),
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.detail || `HTTP ${response.status}`);
      setState(result);
      setMessage(`Switch queued: ${protocol} ${profile}. Waiting for device and telemetry verification.`);
    } catch (err) { setMessage(`Switch not accepted: ${err.message}`); setBusy(false); }
  };

  return (
    <section aria-label="Unified hardware protocol switching" style={{border: "1px solid var(--border, #777)", borderRadius: 10, padding: 16, margin: "16px 0"}}>
      <h3>Real hardware switching — VM-001 / VM-002</h3>
      <p>Independent authenticated control channel. A button press is not success until the vehicle reports and telemetry confirms the mode.</p>
      <div style={{display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center"}}>
        <label>Vehicle <select value={target} onChange={e => {setTarget(e.target.value);setMessage("");}}>{[...new Set([target, ...vehicles.map(v => v.vehicle_id)])].map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Protocol <select value={protocol} onChange={e=>setProtocol(e.target.value)}>{modes.map(p=><option key={p}>{p}</option>)}</select></label>
        <label>Profile <select value={profile} onChange={e=>setProfile(e.target.value)}>{profiles.map(p=><option key={p}>{p}</option>)}</select></label>
        <label>Operator token <input type="password" autoComplete="off" value={operatorToken} onChange={e=>setOperatorToken(e.target.value)} placeholder="Private 64-character token" /></label>
        <button type="button" onClick={switchNow} disabled={!selected?.online || !operatorToken || busy || activeSwitch}>Switch real device</button>
      </div>
      <p>Current observed: {selected ? `${selected.protocol?.toUpperCase()} ${selected.security_profile} — ${selected.online ? "ONLINE" : "OFFLINE"}` : "Not registered"}.
      {" "}Controller: {state?.phase || "unknown"}. {state?.request_id ? `Request ${state.request_id.slice(0, 8)}` : ""}</p>
      {message && <p role="status">{message}</p>}
      <small>DDS disabled until its real firmware and hardware tests pass. Keep the operator token private; use this UI only through a trusted VPN or HTTPS.</small>
    </section>
  );
}


import React from "react";
import researchBundle from "./occ-research-data.json";
import hardwareRows from "./occ-nine-mode-hardware.json";

const profiles = ["C0", "C1", "C2"];
const protocols = [
  { id:"mqtt", label:"MQTT", color:"#38bdf8", key:"MQTT" },
  { id:"opcua", label:"OPC UA", color:"#c4b5fd", key:"OPCUA" },
  { id:"dds", label:"DDS", color:"#6ee7b7", key:"DDS" }
];

const fmt = value => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "—";
};

function hardwareFor(p, level) {
  return hardwareRows.find(r =>
    String(r.protocol || "").toUpperCase().replace(/\s/g, "") === p.key &&
    String(r.security_profile || "").toUpperCase() === level &&
    Number.isFinite(Number(r.mean_timing_ms)) &&
    r.mean_timing_ms !== ""
  );
}

function softwareFor(p, level) {
  const data = researchBundle?.performance?.[p.id] || [];
  const matches = data.filter(r =>
    String(r.security_level || r.security_profile || "").toUpperCase() === level
  );

  const preferred = p.id === "dds" ? "NET-ideal" : "NET-proxy-ideal";

  const row = matches.find(r =>
    (r.network_profile || r.net_profile) === preferred
  );

  if (!row) return null;

  const latency = row.latency_mean_ms;
  if (latency == null || latency === "" || !Number.isFinite(Number(latency)))
    return null;

  return row;
}

function Metric({label, value, suffix=""}) {
  return <div className="occ9metric">
    <span>{label}</span>
    <strong>{fmt(value)}{fmt(value) !== "—" ? suffix : ""}</strong>
  </div>;
}

export default function NineModeEvidenceMatrix({states}) {
  const unknownDDS = false && states?.dds?.online === true &&
    !profiles.includes(
      String(states.dds.security_profile || "").toUpperCase()
    );

  return <section className="panel occ9root">
    <style>{`
      .occ9root { margin-bottom: 16px; }
      .occ9header { display:flex; justify-content:space-between;
                    align-items:center; gap:12px; flex-wrap:wrap; }
      .occ9grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
                  gap:12px; margin-top:16px; }
      .occ9column { display:flex; flex-direction:column; gap:10px; min-width:0; }
      .occ9column h3 { text-align:center; margin:0 0 4px; }
      .occ9card { background:#101b2e; border:1px solid #2b3a52;
                  border-radius:11px; padding:14px; min-height:195px; }
      .occ9card h4 { margin:0; font-size:17px; }
      .occ9top { display:flex; justify-content:space-between; align-items:center; }
      .occ9badge { font-size:10px; padding:4px 7px; border-radius:20px;
                   background:#273750; color:#e0e9f8; font-weight:700; }
      .occ9live { color:#6ee7b7; background:#123f39; }
      .occ9metrics { display:grid; grid-template-columns:1fr 1fr;
                     gap:6px 12px; margin-top:12px; }
      .occ9metric { display:flex; flex-direction:column; gap:2px;
                    min-width:0; font-size:12px; }
      .occ9metric span { color:#9cacbf; }
      .occ9metric strong { color:#eaf2ff; overflow-wrap:anywhere; }
      .occ9note { font-size:11px; color:#aabbd0; margin-top:11px;
                  line-height:1.5; }
      .occ9divider { border:0; border-top:1px solid #304058; margin:12px 0; }
      .occ9unknown { border:1px solid #37516a; border-radius:10px;
                     padding:12px; margin-top:15px; }
      @media(max-width:750px) {
        .occ9grid { grid-template-columns:1fr; }
        .occ9card { min-height:auto; }
      }
    `}</style>

    <div className="occ9header">
      <div>
        <h2>OCC — Nine-mode hardware comparison</h2>
        <p className="muted">
          Recorded hardware pilot measurements for all nine configurations
        </p>
      </div>
      <span className="tag">3 protocols × 3 profiles</span>
    </div>

    <div className="occ9grid">
      {protocols.map(p => <div className="occ9column" key={p.id}>
        <h3 style={{color:p.color}}>{p.label}</h3>
        {profiles.map(level => {
          const vehicle = states?.[p.id];
          const active = false && vehicle?.online === true &&
            String(vehicle.security_profile || "").toUpperCase() === level &&
            !states?.[p.id + "_error"];

          const hw = hardwareFor(p, level);
          const sw = softwareFor(p, level);
          const recorded = !!hw || !!sw;
          const telemetry = active ? (vehicle.telemetry || {}) : {};

          return <article className="occ9card" key={level}
            style={{borderTop:`2px solid ${p.color}`}}>
            <div className="occ9top">
              <h4>{level}</h4>
              <span className={"occ9badge" + (active ? " occ9live" : "")}>
                {active ? "LIVE" : hw ? "RECORDED · HW" :
                  sw ? "RECORDED · SW" : "NO VERIFIED DATA"}
              </span>
            </div>

            {active && <>
              <div className="occ9metrics">
                <Metric label="Sequence" value={vehicle.seq ?? vehicle.sequence}/>
                <Metric label="Speed" value={telemetry.speed}/>
                <Metric label="Battery" value={telemetry.battery_pct ?? telemetry.battery} suffix="%"/>
                <Metric label="Position X" value={telemetry.pos_x}/>
                <Metric label="Position Y" value={telemetry.pos_y}/>
                <div className="occ9metric">
                  <span>Vehicle state</span>
                  <strong>{telemetry.state || "—"}</strong>
                </div>
              </div>
              <p className="occ9note">Fresh VM-001 receiver observation</p>
            </>}

            {recorded && <>
              {active && <hr className="occ9divider"/>}
              <div className="occ9metrics">
                <Metric
                  label={hw ? (hw.timing_metric || "Measured timing") + " (ms)" :
                          "Recorded latency (ms)"}
                  value={hw ? hw.mean_timing_ms : sw.latency_mean_ms}
                />
                <Metric label="Jitter (ms)"
                  value={hw ? hw.mean_jitter_ms : sw.jitter_mean_ms}/>
                <Metric label="Throughput (msg/s)"
                  value={hw ? hw.mean_throughput_msg_s :
                    (sw.throughput_mean_messages_per_second ??
                     sw.throughput_mean_msg_s ?? sw.throughput_mean_mps)}/>
                <Metric label="Loss (%)"
                  value={hw ? hw.mean_loss_percent :
                    (sw.application_delivery_loss_mean_percent ??
                     sw.loss_mean_percent)}/>
              </div>
              <p className="occ9note">
                {hw
                  ? `Hardware pilot · ${hw.timing_scope || "recorded scope"} · ${hw.repeats || "—"} repeats`
                  : `Software experiment · ${sw.network_profile || sw.net_profile || "recorded network"}`}
                {active ? " · Historical KPIs, not live measurements" : ""}
              </p>
            </>}

            {!active && !recorded &&
              <p className="occ9note">
                No matching verified observation in the loaded evidence.
              </p>}
          </article>;
        })}
      </div>)}
    </div>

    {unknownDDS && <div className="occ9unknown">
      <strong>DDS — Live telemetry, security unclassified</strong>
      <p className="occ9note">
        VM-001 is transmitting fresh DDS data. The observer reports
        security profile UNKNOWN, so these samples are not assigned
        to C0, C1 or C2 without independent verification.
      </p>
      <div className="occ9metrics">
        <Metric label="Sequence" value={states.dds.seq}/>
        <Metric label="Speed" value={states.dds.telemetry?.speed}/>
        <Metric label="Battery" value={states.dds.telemetry?.battery_pct} suffix="%"/>
        <Metric label="Position X" value={states.dds.telemetry?.pos_x}/>
      </div>
    </div>}

    <p className="occ9note">
      Hardware round-trip measurements are not interchangeable with
      one-way latency. Software/network baselines can differ between
      protocols. Recorded results do not imply current live connectivity
      or prove ESP32-to-XRCE transport security.
    </p>
  </section>;
}

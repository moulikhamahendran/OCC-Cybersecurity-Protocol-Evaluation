
import { useEffect, useState } from "react";
import "./NineModeMatrix.css";

const PROTOCOLS = [
  { key: "mqtt", name: "MQTT" },
  { key: "opcua", name: "OPC UA" },
  { key: "dds", name: "DDS" }
];
const LEVELS = ["C0", "C1", "C2"];

const LABELS = {
  mqtt: ["Plain", "Credentials", "TLS + credentials"],
  opcua: ["None", "Sign", "Sign & Encrypt"],
  dds: ["Baseline", "DDS participant signing", "DDS participant encryption"]
};

function format(value, unit = "") {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number" && Number.isFinite(value)) {
    return `${Number(value.toFixed(2))}${unit}`;
  }
  return `${value}${unit}`;
}

function Telemetry({ vehicle }) {
  const t = vehicle?.telemetry || {};
  const fields = [
    ["Sequence", vehicle?.seq ?? vehicle?.sequence],
    ["Speed", t.speed],
    ["Battery", t.battery_pct ?? t.battery, "%"],
    ["Position X", t.pos_x],
    ["Position Y", t.pos_y],
    ["Heading", t.heading, "°"],
    ["Vehicle state", t.state]
  ];

  return (
    <dl className="nine-mode-data">
      {fields.map(([name, value, unit]) => (
        <div key={name}>
          <dt>{name}</dt>
          <dd>{format(value, unit || "")}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function NineModeMatrix({ states }) {
  const [observations, setObservations] = useState({});

  useEffect(() => {
    setObservations(previous => {
      const next = { ...previous };
      let changed = false;

      for (const protocol of PROTOCOLS) {
        const v = states[protocol.key];

        if (!v || v.online !== true ||
            states[protocol.key + "_error"]) continue;

        const level = String(v.security_profile || "UNKNOWN").toUpperCase();
        const seq = v.seq ?? v.sequence;

        if (!LEVELS.includes(level) ||
            !v.vehicle_id ||
            seq === null || seq === undefined) continue;

        const key = `${protocol.key}:${level}:${v.vehicle_id}`;
        if (next[key]?.seq === seq) continue;

        next[key] = {
          ...v,
          observedAt: new Date().toLocaleTimeString(),
          receivedAtMs: Date.now()
        };
        changed = true;
      }
      return changed ? next : previous;
    });
  }, [states]);

  return (
    <section className="nine-mode-panel">
      <div className="nine-mode-heading">
        <div>
          <h2>OCC — Nine-mode operational matrix</h2>
          <p>Live receiver data and last observed browser-session snapshots</p>
        </div>
        <span className="nine-mode-count">3 protocols × 3 profiles</span>
      </div>

      <div className="nine-mode-grid">
        {PROTOCOLS.map(protocol => {
          const current = states[protocol.key];
          const error = states[protocol.key + "_error"];
          return (
            <div className="nine-mode-column" key={protocol.key}>
              <h3>{protocol.name}</h3>

              {LEVELS.map((level, index) => {
                const matched = current &&
                  String(current.security_profile || "").toUpperCase() === level;

                const live = matched && current.online === true && !error;
                const storedKey = `${protocol.key}:${level}:${current?.vehicle_id || "VM-001"}`;
                const previous = observations[storedKey];
                const shown = live ? current : previous;
                const status = error
                  ? "API ERROR"
                  : live ? "LIVE"
                  : previous ? "LAST OBSERVED"
                  : "NO DATA";

                const age = live
                  ? current.source_age_seconds ?? current.age_seconds
                  : null;

                return (
                  <article
                    key={level}
                    className={"nine-mode-cell " +
                      (live ? "nine-mode-live" : "")}
                  >
                    <div className="nine-mode-cell-top">
                      <strong>{level}</strong>
                      <span className={
                        "nine-mode-chip " + (live ? "live" : "")
                      }>{status}</span>
                    </div>

                    <p className="nine-mode-description">
                      {LABELS[protocol.key][index]}
                    </p>

                    <p style={{fontSize:12}}>
                      Vehicle: {shown?.vehicle_id || "—"}
                    </p>

                    {shown ? <Telemetry vehicle={shown} /> :
                      <p className="nine-mode-description">
                        No verified observation for this configuration.
                      </p>}

                    <small>
                      {live
                        ? `Live receiver age: ${format(age, " s")}`
                        : previous
                          ? `Browser-session snapshot: ${previous.observedAt}. Not live.`
                          : "Awaiting mode activation and verified telemetry"}
                    </small>
                  </article>
                );
              })}
            </div>
          );
        })}
      </div>

      {PROTOCOLS.map(protocol => {
        const v = states[protocol.key];
        const profile = String(v?.security_profile || "UNKNOWN").toUpperCase();

        if (!v || v.online !== true ||
            states[protocol.key + "_error"] ||
            LEVELS.includes(profile)) return null;

        return (
          <article className="nine-mode-cell" key={protocol.key}
            style={{marginTop:16}}>
            <strong>{protocol.name} — Unclassified live telemetry</strong>
            <p className="nine-mode-description">
              Receiver profile: {profile}. Data is real, but its
              security level is not established.
            </p>
            <p>Vehicle: {v.vehicle_id || "—"}</p>
            <Telemetry vehicle={v} />
          </article>
        );
      })}

      <p className="nine-mode-disclaimer">
        LIVE means fresh operational receiver telemetry, not a
        formal benchmark or proof of cryptographic enforcement.
        LAST OBSERVED records exist only for the current browser
        session and are not persistent historical evidence.
        DDS-Security at the participant layer does not itself
        secure the ESP32 XRCE uplink.
      </p>
    </section>
  );
}

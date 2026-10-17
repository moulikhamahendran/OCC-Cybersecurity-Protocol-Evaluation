import { useEffect, useState } from "react";
import "./OpcuaEvidencePanel.css";

const API_BASE = (
  import.meta.env.VITE_API_BASE ||
  window.location.origin
).replace(/\/$/, "");

const EXPECTED_PROFILES = ["C0", "C1", "C2"];

const DESCRIPTIONS = {
  C0: "NoSecurity",
  C1: "Basic256Sha256 · Sign",
  C2: "Basic256Sha256 · SignAndEncrypt",
};

function formatCount(value) {
  return Number(value || 0).toLocaleString("en-US");
}

export default function OpcuaEvidencePanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    async function load() {
      setLoading(true);
      setError("");

      try {
        const response = await fetch(
          `${API_BASE}/api/v1/opcua/evidence`,
          {
            method: "GET",
            cache: "no-store",
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          throw new Error(`API returned HTTP ${response.status}`);
        }

        const result = await response.json();

        if (
          result.available !== true ||
          result.provides_live_online_status !== false
        ) {
          throw new Error(
            "Historical evidence is unavailable or invalid"
          );
        }

        if (active) setData(result);
      } catch (err) {
        if (active && err.name !== "AbortError") {
          setError(err.message || "Evidence request failed");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [reload]);

  const profiles = EXPECTED_PROFILES.map((name) => {
    const record = data?.profiles?.find(
      (profile) => profile.profile === name
    );

    return {
      profile: name,
      receive_events: record?.receive_events ?? 0,
      transmit_events: record?.transmit_events ?? 0,
      matched_rx_tx_pairs:
        record?.matched_rx_tx_pairs ?? 0,
      vehicles: record?.vehicles ?? [],
      available: Boolean(record),
    };
  });

  return (
    <section
      className="opcua-evidence-panel"
      aria-label="OPC UA historical test evidence"
    >
      <div className="opcua-evidence-heading">
        <div>
          <div className="opcua-evidence-eyebrow">
            VERIFIED HARDWARE EVIDENCE
          </div>
          <h2>OPC UA · C0 / C1 / C2</h2>
          <p>
            Raspberry Pi OCC application events from
            the ESP32 testbed.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setReload((value) => value + 1)}
          disabled={loading}
          className="opcua-evidence-refresh"
        >
          {loading ? "Loading…" : "Reload snapshot"}
        </button>
      </div>

      <p className="opcua-evidence-notice">
        Historical evidence snapshot. These counts do
        not establish that a vehicle is currently online.
        MQTT/OPC UA remote switching is not enabled here.
      </p>

      {error && (
        <p className="opcua-evidence-error" role="alert">
          OPC UA evidence unavailable: {error}
        </p>
      )}

      {!error && loading && !data && (
        <p>Loading verified OPC UA evidence…</p>
      )}

      {data && (
        <>
          <div className="opcua-evidence-grid">
            {profiles.map((entry) => (
              <article
                className="opcua-evidence-card"
                key={entry.profile}
              >
                <div className="opcua-evidence-card-title">
                  <strong>{entry.profile}</strong>
                  <span>{DESCRIPTIONS[entry.profile]}</span>
                </div>

                <div className="opcua-evidence-count">
                  {formatCount(entry.matched_rx_tx_pairs)}
                  <small>Matched RX/TX pairs</small>
                </div>

                <div className="opcua-evidence-detail">
                  <span>
                    RX: {formatCount(entry.receive_events)}
                  </span>
                  <span>
                    TX: {formatCount(entry.transmit_events)}
                  </span>
                </div>

                <div className="opcua-evidence-vehicles">
                  Vehicles: {
                    entry.vehicles.length
                      ? entry.vehicles.join(", ")
                      : "No recorded identity"
                  }
                </div>
              </article>
            ))}
          </div>

          <p className="opcua-evidence-footer">
            Source: sanitized OCC OPC UA event snapshot.
            Original FAIR-V1 benchmark records remain separate.
          </p>
        </>
      )}
    </section>
  );
}

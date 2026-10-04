import { useEffect, useMemo, useState } from "react";


const API_BASE = (
  import.meta.env.VITE_API_BASE
  || "http://localhost:18080"
).replace(/\/$/, "");

const WS_BASE = (
  import.meta.env.VITE_WS_BASE
  || "ws://localhost:18080"
).replace(/\/$/, "");


function formatNumber(
  value,
  digits = 1,
) {
  const numeric = Number(value);

  if (!Number.isFinite(numeric)) {
    return "—";
  }

  return numeric.toFixed(digits);
}


function profileClass(profile) {
  return (
    String(profile || "")
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "")
    || "unknown"
  );
}


function deepMetric(
  object,
  names,
) {
  if (!object || typeof object !== "object") {
    return undefined;
  }

  for (const name of names) {
    if (
      Object.prototype.hasOwnProperty.call(
        object,
        name,
      )
    ) {
      return object[name];
    }
  }

  for (const value of Object.values(object)) {
    if (
      value
      && typeof value === "object"
      && !Array.isArray(value)
    ) {
      const nested = deepMetric(
        value,
        names,
      );

      if (nested !== undefined) {
        return nested;
      }
    }
  }

  return undefined;
}


function extractProfiles(bundle) {
  if (!bundle) {
    return [];
  }

  const candidates = [
    bundle.profiles,
    bundle.profile_aggregate,
    bundle.profile_aggregates,
    bundle.aggregates,
    bundle.aggregate,
    bundle.data?.profiles,
    bundle.data?.profile_aggregate,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate;
    }

    if (
      candidate
      && typeof candidate === "object"
    ) {
      const rows = Object.entries(
        candidate,
      )
        .filter(([key]) =>
          /^C[012]$/i.test(key),
        )
        .map(([profile, value]) => ({
          profile,
          ...(value || {}),
        }));

      if (rows.length) {
        return rows;
      }
    }
  }

  return [];
}


function metricForProfile(
  rows,
  profile,
  names,
) {
  const row = rows.find(
    (item) =>
      String(
        item.profile
        ?? item.security_profile
        ?? "",
      ).toUpperCase()
      === profile,
  );

  return deepMetric(
    row,
    names,
  );
}


function StatusDot({
  ok,
}) {
  return (
    <span
      className={
        ok
          ? "status-dot online"
          : "status-dot offline"
      }
    />
  );
}


function ProfileBadge({
  profile,
}) {
  return (
    <span
      className={
        `profile-badge ${profileClass(profile)}`
      }
    >
      {profile || "—"}
    </span>
  );
}


function MetricCard({
  label,
  value,
  unit,
  helper,
}) {
  return (
    <article className="metric-card">
      <div className="metric-label">
        {label}
      </div>

      <div className="metric-value">
        {value}
        {unit && (
          <span className="metric-unit">
            {unit}
          </span>
        )}
      </div>

      {helper && (
        <div className="metric-helper">
          {helper}
        </div>
      )}
    </article>
  );
}


function VehicleCard({
  vehicle,
}) {
  const telemetry = vehicle.telemetry || {};

  return (
    <article className="vehicle-card">
      <div className="vehicle-card-header">
        <div>
          <div className="eyebrow">
            AGV COMMUNICATION NODE
          </div>

          <h3>
            {vehicle.vehicle_id}
          </h3>
        </div>

        <div className="vehicle-status">
          <StatusDot
            ok={vehicle.online}
          />

          {vehicle.online
            ? "ONLINE"
            : "OFFLINE"}
        </div>
      </div>

      <div className="vehicle-meta">
        <div>
          <span>Protocol</span>
          <strong>
            {String(
              vehicle.protocol || "—",
            ).toUpperCase()}
          </strong>
        </div>

        <div>
          <span>Security</span>
          <ProfileBadge
            profile={
              vehicle.security_profile
            }
          />
        </div>

        <div>
          <span>Sequence</span>
          <strong>
            {vehicle.seq ?? "—"}
          </strong>
        </div>
      </div>

      <div className="telemetry-grid">
        <div>
          <span>Speed</span>
          <strong>
            {formatNumber(
              telemetry.speed,
              2,
            )}
          </strong>
          <small>m/s</small>
        </div>

        <div>
          <span>Battery</span>
          <strong>
            {formatNumber(
              telemetry.battery_pct,
              0,
            )}
          </strong>
          <small>%</small>
        </div>

        <div>
          <span>Position X</span>
          <strong>
            {formatNumber(
              telemetry.pos_x,
              2,
            )}
          </strong>
        </div>

        <div>
          <span>Position Y</span>
          <strong>
            {formatNumber(
              telemetry.pos_y,
              2,
            )}
          </strong>
        </div>

        <div>
          <span>Heading</span>
          <strong>
            {formatNumber(
              telemetry.heading,
              1,
            )}
          </strong>
          <small>°</small>
        </div>

        <div>
          <span>State</span>
          <strong>
            {telemetry.state || "—"}
          </strong>
        </div>
      </div>

      <div className="vehicle-footer">
        <span>
          Age
        </span>

        <strong>
          {formatNumber(
            vehicle.age_seconds,
            2,
          )} s
        </strong>
      </div>
    </article>
  );
}


function SecurityProfileCard({
  profile,
  rows,
}) {
  const rtt = metricForProfile(
    rows,
    profile,
    [
      "rtt_mean_of_repeat_means_ms",
      "mean_rtt_ms",
      "rtt_mean_ms",
    ],
  );

  const jitter = metricForProfile(
    rows,
    profile,
    [
      "jitter_mean_of_repeats_ms",
      "mean_jitter_ms",
      "jitter_ms",
    ],
  );

  const achieved = metricForProfile(
    rows,
    profile,
    [
      "achieved_rate_mean_percent",
      "achieved_rate_percent",
    ],
  );

  const unsuccessful = metricForProfile(
    rows,
    profile,
    [
      "unsuccessful_transaction_mean_percent",
      "unsuccessful_percent",
    ],
  );

  return (
    <article
      className={
        `security-card ${profileClass(profile)}`
      }
    >
      <div className="security-card-title">
        <ProfileBadge
          profile={profile}
        />

        <span>
          MQTT qualification
        </span>
      </div>

      <div className="security-rtt">
        {formatNumber(
          rtt,
          1,
        )}
        <small>ms RTT</small>
      </div>

      <div className="security-details">
        <div>
          <span>Jitter</span>
          <strong>
            {formatNumber(
              jitter,
              1,
            )} ms
          </strong>
        </div>

        <div>
          <span>Achieved rate</span>
          <strong>
            {formatNumber(
              achieved,
              2,
            )}%
          </strong>
        </div>

        <div>
          <span>Unsuccessful tx</span>
          <strong>
            {formatNumber(
              unsuccessful,
              2,
            )}%
          </strong>
        </div>
      </div>
    </article>
  );
}


function App() {
  const [fleet, setFleet] = useState({
    vehicles: [],
    vehicle_count: 0,
    online_count: 0,
  });

  const [
    socketState,
    setSocketState,
  ] = useState("connecting");

  const [
    health,
    setHealth,
  ] = useState(null);

  const [
    mqttStatus,
    setMqttStatus,
  ] = useState(null);

  const [
    benchmark,
    setBenchmark,
  ] = useState(null);

  const [
    benchmarkStatus,
    setBenchmarkStatus,
  ] = useState(null);

  const [
    error,
    setError,
  ] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function getJson(path) {
      const response = await fetch(
        `${API_BASE}${path}`,
      );

      if (!response.ok) {
        throw new Error(
          `${path}: HTTP ${response.status}`,
        );
      }

      return response.json();
    }

    async function loadInitial() {
      const requests = await Promise.allSettled([
        getJson("/api/v1/health"),
        getJson(
          "/api/v1/mqtt/live/status",
        ),
        getJson(
          "/api/v1/benchmark/mqtt/qualification",
        ),
        getJson(
          "/api/v1/benchmark/mqtt/qualification/status",
        ),
        getJson("/api/v1/vehicles"),
      ]);

      if (cancelled) {
        return;
      }

      const [
        healthResult,
        mqttResult,
        benchmarkResult,
        benchmarkStatusResult,
        fleetResult,
      ] = requests;

      if (
        healthResult.status === "fulfilled"
      ) {
        setHealth(
          healthResult.value,
        );
      }

      if (
        mqttResult.status === "fulfilled"
      ) {
        setMqttStatus(
          mqttResult.value,
        );
      }

      if (
        benchmarkResult.status
        === "fulfilled"
      ) {
        setBenchmark(
          benchmarkResult.value,
        );
      }

      if (
        benchmarkStatusResult.status
        === "fulfilled"
      ) {
        setBenchmarkStatus(
          benchmarkStatusResult.value,
        );
      }

      if (
        fleetResult.status
        === "fulfilled"
      ) {
        setFleet(
          fleetResult.value,
        );
      }

      const failures = requests.filter(
        (item) =>
          item.status === "rejected",
      );

      if (failures.length) {
        setError(
          "Some backend data is unavailable.",
        );
      }
    }

    loadInitial();

    return () => {
      cancelled = true;
    };
  }, []);


  useEffect(() => {
    let socket;
    let reconnectTimer;
    let stopped = false;

    function connect() {
      if (stopped) {
        return;
      }

      setSocketState("connecting");

      socket = new WebSocket(
        `${WS_BASE}/api/v1/ws/vehicles`,
      );

      socket.onopen = () => {
        setSocketState("connected");
        setError("");
      };

      socket.onmessage = (event) => {
        try {
          setFleet(
            JSON.parse(
              event.data,
            ),
          );
        } catch {
          setError(
            "Invalid WebSocket payload.",
          );
        }
      };

      socket.onerror = () => {
        setSocketState("error");
      };

      socket.onclose = () => {
        if (stopped) {
          return;
        }

        setSocketState(
          "disconnected",
        );

        reconnectTimer = window.setTimeout(
          connect,
          2000,
        );
      };
    }

    connect();

    return () => {
      stopped = true;

      window.clearTimeout(
        reconnectTimer,
      );

      socket?.close();
    };
  }, []);


  const profileRows = useMemo(
    () => extractProfiles(
      benchmark,
    ),
    [benchmark],
  );


  const connectedProfiles = (
    mqttStatus?.profiles
    || []
  ).filter(
    (profile) =>
      profile.connected,
  ).length;


  const totalAccepted = (
    mqttStatus?.profiles
    || []
  ).reduce(
    (sum, profile) =>
      sum
      + Number(
        profile.accepted_messages
        || 0,
      ),
    0,
  );


  const liveConnected = (
    socketState === "connected"
  );


  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            O
          </div>

          <div>
            <strong>
              OCC
            </strong>
            <span>
              Cybersecurity Platform
            </span>
          </div>
        </div>

        <nav>
          <a
            href="#overview"
            className="active"
          >
            Overview
          </a>

          <a href="#fleet">
            Live Fleet
          </a>

          <a href="#security">
            Security Profiles
          </a>

          <a href="#benchmark">
            Benchmark
          </a>
        </nav>

        <div className="sidebar-footer">
          <div className="read-only">
            <span>READ ONLY</span>
            Monitoring mode
          </div>

          <small>
            FAIR-V1 measurement path
            remains separate.
          </small>
        </div>
      </aside>

      <main className="main-content">
        <section
          className="topbar"
          id="overview"
        >
          <div>
            <div className="eyebrow">
              OCC / MQTT OPERATIONAL VIEW
            </div>

            <h1>
              Cybersecurity
              <span> Control Center</span>
            </h1>

            <p>
              Live AGV telemetry,
              security-profile status,
              and qualification KPIs.
            </p>
          </div>

          <div className="top-status">
            <div>
              <StatusDot
                ok={Boolean(health)}
              />
              API
            </div>

            <div>
              <StatusDot
                ok={liveConnected}
              />
              Live stream
            </div>
          </div>
        </section>

        {error && (
          <div className="notice">
            {error}
          </div>
        )}

        <section className="summary-grid">
          <MetricCard
            label="Vehicles online"
            value={
              fleet.online_count ?? 0
            }
            helper={
              `${fleet.vehicle_count ?? 0} discovered`
            }
          />

          <MetricCard
            label="MQTT profiles"
            value={connectedProfiles}
            unit="/ 3"
            helper="C0 · C1 · C2"
          />

          <MetricCard
            label="Accepted telemetry"
            value={totalAccepted}
            helper="Dashboard observer"
          />

          <MetricCard
            label="Live channel"
            value={
              liveConnected
                ? "LIVE"
                : "WAIT"
            }
            helper="WebSocket · 4 Hz UI refresh"
          />
        </section>

        <section
          className="section"
          id="fleet"
        >
          <div className="section-header">
            <div>
              <div className="eyebrow">
                REAL-TIME OPERATION
              </div>

              <h2>
                Live Vehicle Fleet
              </h2>
            </div>

            <div
              className={
                `connection-pill ${
                  liveConnected
                    ? "connected"
                    : ""
                }`
              }
            >
              <StatusDot
                ok={liveConnected}
              />

              {socketState}
            </div>
          </div>

          <div className="vehicle-grid">
            {fleet.vehicles?.length
              ? fleet.vehicles.map(
                  (vehicle) => (
                    <VehicleCard
                      key={
                        vehicle.vehicle_id
                      }
                      vehicle={vehicle}
                    />
                  ),
                )
              : (
                <div className="empty-state">
                  Waiting for live vehicle
                  telemetry…
                </div>
              )}
          </div>
        </section>

        <section
          className="section"
          id="security"
        >
          <div className="section-header">
            <div>
              <div className="eyebrow">
                MQTT SECURITY
              </div>

              <h2>
                Security Profile
                Comparison
              </h2>
            </div>

            <div className="qualification-tag">
              Qualification dataset
            </div>
          </div>

          <div className="security-grid">
            {["C0", "C1", "C2"].map(
              (profile) => (
                <SecurityProfileCard
                  key={profile}
                  profile={profile}
                  rows={profileRows}
                />
              ),
            )}
          </div>

          <div className="method-note">
            <strong>
              Interpretation:
            </strong>{" "}
            KPI values are derived from
            the sequential MQTT
            qualification dataset. They
            are not being relabelled as
            the final interleaved
            cross-protocol FAIR-V1
            campaign.
          </div>
        </section>

        <section
          className="section"
          id="benchmark"
        >
          <div className="section-header">
            <div>
              <div className="eyebrow">
                EVIDENCE
              </div>

              <h2>
                Benchmark Status
              </h2>
            </div>
          </div>

          <div className="benchmark-panel">
            <div>
              <span>
                Dataset
              </span>

              <strong>
                MQTT Qualification
              </strong>
            </div>

            <div>
              <span>
                API status
              </span>

              <strong>
                {
                  benchmarkStatus
                    ? "AVAILABLE"
                    : "WAITING"
                }
              </strong>
            </div>

            <div>
              <span>
                Security conditions
              </span>

              <strong>
                C0 / C1 / C2
              </strong>
            </div>

            <div>
              <span>
                Dashboard role
              </span>

              <strong>
                Presentation only
              </strong>
            </div>
          </div>
        </section>

        <footer>
          <span>
            OCC Cybersecurity Protocol
            Evaluation
          </span>

          <span>
            MQTT · OPC UA · DDS
          </span>
        </footer>
      </main>
    </div>
  );
}


export default App;

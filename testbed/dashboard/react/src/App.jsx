import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import "./App.css";


const API_BASE = (
  import.meta.env.VITE_API_BASE
  || window.location.origin
).replace(/\/$/, "");

const DEFAULT_WS_BASE = (
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
);

const WS_BASE = (
  import.meta.env.VITE_WS_BASE
  || DEFAULT_WS_BASE
).replace(/\/$/, "");

const PROFILES = [
  "C0",
  "C1",
  "C2",
];

const TERMINAL_PHASES = new Set([
  "verified",
  "failed",
  "timeout",
]);

const PROFILE_INFO = {
  C0: {
    name: "Open",
    description: "No MQTT authentication or TLS",
  },
  C1: {
    name: "Authenticated",
    description: "Username/password authentication",
  },
  C2: {
    name: "Protected",
    description: "Authentication + verified TLS",
  },
};


async function apiJson(
  path,
  options = {},
) {
  const response = await fetch(
    `${API_BASE}${path}`,
    {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    },
  );

  if (!response.ok) {
    let detail = (
      `${response.status} ${response.statusText}`
    );

    try {
      const body = await response.json();

      if (body?.detail) {
        detail = body.detail;
      }
    } catch {
      // Preserve HTTP fallback.
    }

    throw new Error(detail);
  }

  return response.json();
}


function sleep(ms) {
  return new Promise(
    (resolve) => setTimeout(
      resolve,
      ms,
    ),
  );
}


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


function formatTime(value) {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (
    Number.isNaN(
      date.getTime(),
    )
  ) {
    return "—";
  }

  return date.toLocaleTimeString(
    [],
    {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    },
  );
}


function deepMetric(
  object,
  names,
) {
  if (
    !object
    || typeof object !== "object"
  ) {
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

  for (
    const value
    of Object.values(object)
  ) {
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
        .filter(
          ([key]) => /^C[012]$/i.test(
            key,
          ),
        )
        .map(
          ([profile, value]) => ({
            profile,
            ...(value || {}),
          }),
        );

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
    (item) => (
      String(
        item.profile
        ?? item.security_profile
        ?? "",
      ).toUpperCase()
      === profile
    ),
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
        `status-dot ${
          ok
            ? "online"
            : "offline"
        }`
      }
    />
  );
}


function StatusPill({
  ok,
  label,
  helper,
}) {
  return (
    <div className="status-pill">
      <StatusDot ok={ok} />

      <div>
        <strong>{label}</strong>

        {helper && (
          <span>
            {helper}
          </span>
        )}
      </div>
    </div>
  );
}


function ProfileBadge({
  profile,
}) {
  return (
    <span
      className={
        `profile-badge ${
          String(
            profile || "",
          ).toLowerCase()
        }`
      }
    >
      {profile || "—"}
    </span>
  );
}


function Sparkline({
  values,
}) {
  const clean = (
    Array.isArray(values)
      ? values
      : []
  )
    .map(Number)
    .filter(Number.isFinite)
    .slice(-32);

  if (clean.length < 2) {
    return (
      <div className="sparkline-empty">
        waiting for telemetry
      </div>
    );
  }

  const width = 180;
  const height = 42;

  const min = Math.min(
    ...clean,
  );

  const max = Math.max(
    ...clean,
  );

  const spread = (
    max - min
  ) || 1;

  const points = clean
    .map(
      (value, index) => {
        const x = (
          index
          / (
            clean.length - 1
          )
        ) * width;

        const y = (
          height
          - (
            (
              value - min
            )
            / spread
          )
          * (
            height - 6
          )
          - 3
        );

        return `${x},${y}`;
      },
    )
    .join(" ");

  return (
    <svg
      className="sparkline"
      viewBox={
        `0 0 ${width} ${height}`
      }
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        points={points}
      />
    </svg>
  );
}


function ThemeSwitcher({
  value,
  onChange,
}) {
  return (
    <div
      className="theme-switcher"
      aria-label="Appearance"
    >
      <button
        className={
          value === "light"
            ? "selected"
            : ""
        }
        onClick={() => onChange(
          "light",
        )}
        title="Light mode"
      >
        ☀
      </button>

      <button
        className={
          value === "auto"
            ? "selected"
            : ""
        }
        onClick={() => onChange(
          "auto",
        )}
        title="Follow system"
      >
        ◐
      </button>

      <button
        className={
          value === "dark"
            ? "selected"
            : ""
        }
        onClick={() => onChange(
          "dark",
        )}
        title="Dark mode"
      >
        ☾
      </button>
    </div>
  );
}


function SwitchState({
  request,
}) {
  if (!request) {
    return null;
  }

  const phase = (
    request.phase
    || "requested"
  );

  const terminal = (
    TERMINAL_PHASES.has(
      phase,
    )
  );

  return (
    <div
      className={
        `switch-state ${
          terminal
            ? phase
            : "busy"
        }`
      }
    >
      <div className="switch-state-line">
        <span>
          {request.previous_profile}
        </span>

        <span className="switch-arrow">
          →
        </span>

        <strong>
          {request.target_profile}
        </strong>

        <span className="switch-phase">
          {phase
            .replaceAll(
              "_",
              " ",
            )}
        </span>
      </div>

      {!terminal && (
        <div className="switch-progress">
          <span />
        </div>
      )}

      {request.error && (
        <div className="switch-error">
          {request.error}
        </div>
      )}
    </div>
  );
}


function VehicleCard({
  vehicle,
  controlState,
  controlReady,
  history,
  onSwitch,
  onOpen,
}) {
  const telemetry = (
    vehicle.telemetry || {}
  );

  const request = (
    controlState?.request
    || null
  );

  const busy = Boolean(
    request
    && !TERMINAL_PHASES.has(
      request.phase,
    ),
  );

  return (
    <article
      className={
        `vehicle-card ${
          vehicle.online
            ? "vehicle-online"
            : "vehicle-offline"
        }`
      }
    >
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

      <div className="vehicle-profile-line">
        <span>
          MQTT
        </span>

        <span className="slash">
          /
        </span>

        <ProfileBadge
          profile={
            vehicle.security_profile
          }
        />

        <span className="profile-name">
          {
            PROFILE_INFO[
              vehicle.security_profile
            ]?.name
            || ""
          }
        </span>
      </div>

      <div className="profile-controls">
        {PROFILES.map(
          (profile) => {
            const active = (
              vehicle.security_profile
              === profile
            );

            const requested = (
              busy
              && request?.target_profile
              === profile
            );

            return (
              <button
                key={profile}
                className={
                  `profile-control ${
                    active
                      ? "active"
                      : ""
                  } ${
                    requested
                      ? "requested"
                      : ""
                  }`
                }
                disabled={
                  !vehicle.online
                  || !controlReady
                  || busy
                  || active
                }
                onClick={() => onSwitch(
                  vehicle,
                  profile,
                )}
              >
                <strong>
                  {profile}
                </strong>

                <small>
                  {
                    PROFILE_INFO[
                      profile
                    ].name
                  }
                </small>
              </button>
            );
          },
        )}
      </div>

      <SwitchState
        request={request}
      />

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
          <span>Position</span>
          <strong>
            {formatNumber(
              telemetry.pos_x,
              1,
            )}
            {" / "}
            {formatNumber(
              telemetry.pos_y,
              1,
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

        <div>
          <span>Sequence</span>
          <strong>
            {vehicle.seq ?? "—"}
          </strong>
        </div>
      </div>

      <div className="vehicle-heartbeat">
        <div>
          <span>
            Live sequence
          </span>

          <small>
            {formatNumber(
              vehicle.age_seconds,
              2,
            )} s ago
          </small>
        </div>

        <Sparkline
          values={history}
        />
      </div>

      <button
        className="details-button"
        onClick={() => onOpen(
          vehicle.vehicle_id,
        )}
      >
        View details
        <span>→</span>
      </button>
    </article>
  );
}


function Topology({
  vehicles,
  mqttLive,
}) {
  const brokerConnected = (
    mqttLive?.profiles
    || []
  ).every(
    (item) => item.connected,
  );

  return (
    <section className="panel topology-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">
            LIVE ARCHITECTURE
          </div>

          <h2>
            OCC topology
          </h2>
        </div>

        <span className="live-label">
          LIVE
        </span>
      </div>

      <div className="topology">
        <div className="topology-column">
          {vehicles.map(
            (vehicle) => (
              <div
                key={
                  vehicle.vehicle_id
                }
                className="topology-node vehicle-node"
              >
                <StatusDot
                  ok={vehicle.online}
                />

                <div>
                  <strong>
                    {vehicle.vehicle_id}
                  </strong>

                  <small>
                    MQTT · {
                      vehicle
                        .security_profile
                    }
                  </small>
                </div>
              </div>
            ),
          )}
        </div>

        <div className="topology-link">
          <span />
          <small>
            Wi-Fi / LAN
          </small>
        </div>

        <div className="topology-node">
          <StatusDot
            ok={brokerConnected}
          />

          <div>
            <strong>
              Mosquitto
            </strong>

            <small>
              1883 · 1884 · 8883
            </small>
          </div>
        </div>

        <div className="topology-link">
          <span />
        </div>

        <div className="topology-node">
          <StatusDot
            ok={brokerConnected}
          />

          <div>
            <strong>
              OCC
            </strong>

            <small>
              Raspberry Pi 5
            </small>
          </div>
        </div>

        <div className="topology-link">
          <span />
        </div>

        <div className="topology-node dashboard-node">
          <StatusDot ok />

          <div>
            <strong>
              Dashboard
            </strong>

            <small>
              Control + telemetry
            </small>
          </div>
        </div>
      </div>
    </section>
  );
}


function EventTimeline({
  events,
}) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">
            SESSION ACTIVITY
          </div>

          <h2>
            Security event timeline
          </h2>
        </div>
      </div>

      <div className="timeline">
        {!events.length && (
          <div className="empty-state">
            Profile switch events will
            appear here.
          </div>
        )}

        {events
          .slice(0, 14)
          .map(
            (event, index) => (
              <div
                className="timeline-event"
                key={
                  `${
                    event.timestamp_utc
                  }-${
                    event.vehicle_id
                  }-${
                    event.event
                  }-${index}`
                }
              >
                <span className="timeline-marker" />

                <div className="timeline-time">
                  {formatTime(
                    event.timestamp_utc,
                  )}
                </div>

                <div className="timeline-body">
                  <strong>
                    {event.vehicle_id}
                  </strong>

                  <span>
                    {String(
                      event.event || "",
                    ).replaceAll(
                      "_",
                      " ",
                    )}
                  </span>

                  {event.profile && (
                    <ProfileBadge
                      profile={
                        event.profile
                      }
                    />
                  )}
                </div>
              </div>
            ),
          )}
      </div>
    </section>
  );
}


function QualificationPanel({
  qualification,
}) {
  const rows = useMemo(
    () => extractProfiles(
      qualification,
    ),
    [qualification],
  );

  return (
    <section className="panel qualification-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">
            QUALIFICATION EVIDENCE
          </div>

          <h2>
            MQTT security comparison
          </h2>
        </div>

        <span className="evidence-tag">
          15 qualification runs
        </span>
      </div>

      <div className="qualification-grid">
        {PROFILES.map(
          (profile) => {
            const rtt = (
              metricForProfile(
                rows,
                profile,
                [
                  "rtt_mean_of_repeat_means_ms",
                  "mean_rtt_repeat_mean_ms",
                  "mean_timing_ms",
                  "mean_rtt_ms",
                  "rtt_mean_ms",
                ],
              )
            );

            const jitter = (
              metricForProfile(
                rows,
                profile,
                [
                  "jitter_mean_of_repeats_ms",
                  "mean_jitter_repeat_mean_ms",
                  "mean_jitter_ms",
                  "jitter_mean_ms",
                  "jitter_ms",
                ],
              )
            );

            const achieved = (
              metricForProfile(
                rows,
                profile,
                [
                  "achieved_rate_mean_percent",
                  "mean_achieved_rate_pct",
                  "achieved_rate_pct",
                  "achieved_rate",
                ],
              )
            );

            const unsuccessful = (
              metricForProfile(
                rows,
                profile,
                [
                  "unsuccessful_transaction_mean_percent",
                  "mean_unsuccessful_pct",
                  "unsuccessful_pct",
                  "transaction_failure_pct",
                ],
              )
            );

            return (
              <article
                className={
                  `qualification-card ${
                    profile.toLowerCase()
                  }`
                }
                key={profile}
              >
                <div className="qualification-title">
                  <ProfileBadge
                    profile={profile}
                  />

                  <div>
                    <strong>
                      {
                        PROFILE_INFO[
                          profile
                        ].name
                      }
                    </strong>

                    <span>
                      {
                        PROFILE_INFO[
                          profile
                        ].description
                      }
                    </span>
                  </div>
                </div>

                <div className="qualification-values">
                  <div>
                    <span>
                      Mean RTT
                    </span>

                    <strong>
                      {formatNumber(
                        rtt,
                        1,
                      )}
                    </strong>

                    <small>ms</small>
                  </div>

                  <div>
                    <span>
                      Jitter
                    </span>

                    <strong>
                      {formatNumber(
                        jitter,
                        1,
                      )}
                    </strong>

                    <small>ms</small>
                  </div>

                  <div>
                    <span>
                      Achieved
                    </span>

                    <strong>
                      {formatNumber(
                        achieved,
                        2,
                      )}
                    </strong>

                    <small>%</small>
                  </div>

                  <div>
                    <span>
                      Unsuccessful
                    </span>

                    <strong>
                      {formatNumber(
                        unsuccessful,
                        2,
                      )}
                    </strong>

                    <small>%</small>
                  </div>
                </div>
              </article>
            );
          },
        )}
      </div>

      <div className="qualification-note">
        Qualification evidence is the
        preserved sequential MQTT
        engineering dataset. It is not
        being presented as the final
        interleaved MQTT/OPC UA/DDS FAIR
        comparison campaign.
      </div>
    </section>
  );
}


function VehicleDrawer({
  vehicle,
  controlState,
  onClose,
}) {
  if (!vehicle) {
    return null;
  }

  const telemetry = (
    vehicle.telemetry || {}
  );

  const events = (
    controlState?.recent_events
    || []
  )
    .slice()
    .reverse();

  return (
    <div
      className="drawer-backdrop"
      onMouseDown={onClose}
    >
      <aside
        className="vehicle-drawer"
        onMouseDown={
          (event) => (
            event.stopPropagation()
          )
        }
      >
        <button
          className="drawer-close"
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>

        <div className="eyebrow">
          VEHICLE DETAIL
        </div>

        <h2>
          {vehicle.vehicle_id}
        </h2>

        <div className="drawer-status">
          <StatusPill
            ok={vehicle.online}
            label={
              vehicle.online
                ? "Online"
                : "Offline"
            }
            helper={
              `last seen ${
                formatNumber(
                  vehicle.age_seconds,
                  2,
                )
              } s ago`
            }
          />

          <div>
            <span>Security</span>
            <ProfileBadge
              profile={
                vehicle.security_profile
              }
            />
          </div>
        </div>

        <SwitchState
          request={
            controlState?.request
          }
        />

        <div className="drawer-grid">
          <div>
            <span>Protocol</span>
            <strong>MQTT</strong>
          </div>

          <div>
            <span>Sequence</span>
            <strong>
              {vehicle.seq ?? "—"}
            </strong>
          </div>

          <div>
            <span>Speed</span>
            <strong>
              {formatNumber(
                telemetry.speed,
                2,
              )} m/s
            </strong>
          </div>

          <div>
            <span>Battery</span>
            <strong>
              {formatNumber(
                telemetry.battery_pct,
                0,
              )} %
            </strong>
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
              )}°
            </strong>
          </div>

          <div>
            <span>State</span>
            <strong>
              {telemetry.state || "—"}
            </strong>
          </div>
        </div>

        <div className="drawer-events">
          <h3>
            Recent security events
          </h3>

          {!events.length && (
            <div className="empty-state">
              No profile-switch events
              in this dashboard session.
            </div>
          )}

          {events.map(
            (event, index) => (
              <div
                className="drawer-event"
                key={
                  `${
                    event.timestamp_utc
                  }-${index}`
                }
              >
                <span>
                  {formatTime(
                    event.timestamp_utc,
                  )}
                </span>

                <strong>
                  {String(
                    event.event || "",
                  ).replaceAll(
                    "_",
                    " ",
                  )}
                </strong>

                {event.profile && (
                  <ProfileBadge
                    profile={
                      event.profile
                    }
                  />
                )}
              </div>
            ),
          )}
        </div>
      </aside>
    </div>
  );
}


export default function App() {
  const [
    theme,
    setTheme,
  ] = useState(
    () => (
      localStorage.getItem(
        "occ-dashboard-theme",
      )
      || "auto"
    ),
  );

  const [
    demoMode,
    setDemoMode,
  ] = useState(false);

  const [
    health,
    setHealth,
  ] = useState(null);

  const [
    mqttLive,
    setMqttLive,
  ] = useState(null);

  const [
    controlStatus,
    setControlStatus,
  ] = useState(null);

  const [
    qualification,
    setQualification,
  ] = useState(null);

  const [
    fleet,
    setFleet,
  ] = useState({
    vehicle_count: 0,
    online_count: 0,
    vehicles: [],
  });

  const [
    wsState,
    setWsState,
  ] = useState("connecting");

  const [
    controlStates,
    setControlStates,
  ] = useState({});

  const [
    histories,
    setHistories,
  ] = useState({});

  const [
    selectedVehicleId,
    setSelectedVehicleId,
  ] = useState(null);

  const [
    toast,
    setToast,
  ] = useState(null);


  useEffect(
    () => {
      const media = (
        window.matchMedia(
          "(prefers-color-scheme: dark)",
        )
      );

      const apply = () => {
        const dark = (
          theme === "dark"
          || (
            theme === "auto"
            && media.matches
          )
        );

        document.documentElement
          .dataset.theme = (
            dark
              ? "dark"
              : "light"
          );
      };

      localStorage.setItem(
        "occ-dashboard-theme",
        theme,
      );

      apply();

      media.addEventListener(
        "change",
        apply,
      );

      return () => {
        media.removeEventListener(
          "change",
          apply,
        );
      };
    },
    [theme],
  );


  useEffect(
    () => {
      if (!toast) {
        return undefined;
      }

      const timer = setTimeout(
        () => setToast(null),
        5000,
      );

      return () => clearTimeout(
        timer,
      );
    },
    [toast],
  );


  useEffect(
    () => {
      const handleKey = (
        event,
      ) => {
        if (event.key === "Escape") {
          setSelectedVehicleId(
            null,
          );
        }
      };

      window.addEventListener(
        "keydown",
        handleKey,
      );

      return () => (
        window.removeEventListener(
          "keydown",
          handleKey,
        )
      );
    },
    [],
  );


  const updateHistories = useCallback(
    (vehicles) => {
      setHistories(
        (previous) => {
          const next = {
            ...previous,
          };

          for (
            const vehicle
            of vehicles || []
          ) {
            if (
              !Number.isFinite(
                Number(
                  vehicle.seq,
                ),
              )
            ) {
              continue;
            }

            const current = (
              next[
                vehicle.vehicle_id
              ] || []
            );

            const value = Number(
              vehicle.seq,
            );

            if (
              current[
                current.length - 1
              ] === value
            ) {
              continue;
            }

            next[
              vehicle.vehicle_id
            ] = [
              ...current,
              value,
            ].slice(-32);
          }

          return next;
        },
      );
    },
    [],
  );


  const applyFleet = useCallback(
    (snapshot) => {
      if (
        !snapshot
        || !Array.isArray(
          snapshot.vehicles,
        )
      ) {
        return;
      }

      setFleet(snapshot);

      updateHistories(
        snapshot.vehicles,
      );
    },
    [updateHistories],
  );


  const refreshSystem = useCallback(
    async () => {
      const results = await Promise.allSettled([
        apiJson(
          "/api/v1/health",
        ),
        apiJson(
          "/api/v1/mqtt/live/status",
        ),
        apiJson(
          "/api/v1/mqtt/control/status",
        ),
        apiJson(
          "/api/v1/benchmark/mqtt/qualification",
        ),
        apiJson(
          "/api/v1/vehicles",
        ),
      ]);

      if (
        results[0].status
        === "fulfilled"
      ) {
        setHealth(
          results[0].value,
        );
      }

      if (
        results[1].status
        === "fulfilled"
      ) {
        setMqttLive(
          results[1].value,
        );
      }

      if (
        results[2].status
        === "fulfilled"
      ) {
        setControlStatus(
          results[2].value,
        );
      }

      if (
        results[3].status
        === "fulfilled"
      ) {
        setQualification(
          results[3].value,
        );
      }

      if (
        results[4].status
        === "fulfilled"
      ) {
        applyFleet(
          results[4].value,
        );
      }
    },
    [applyFleet],
  );


  useEffect(
    () => {
      refreshSystem();

      const timer = setInterval(
        refreshSystem,
        5000,
      );

      return () => clearInterval(
        timer,
      );
    },
    [refreshSystem],
  );


  useEffect(
    () => {
      let socket = null;
      let reconnectTimer = null;
      let stopped = false;

      const connect = () => {
        if (stopped) {
          return;
        }

        setWsState(
          "connecting",
        );

        socket = new WebSocket(
          `${WS_BASE}/api/v1/ws/vehicles`,
        );

        socket.onopen = () => {
          setWsState(
            "connected",
          );
        };

        socket.onmessage = (
          event,
        ) => {
          try {
            applyFleet(
              JSON.parse(
                event.data,
              ),
            );
          } catch {
            // Ignore malformed presentation message.
          }
        };

        socket.onerror = () => {
          setWsState(
            "error",
          );
        };

        socket.onclose = () => {
          if (stopped) {
            return;
          }

          setWsState(
            "disconnected",
          );

          reconnectTimer = setTimeout(
            connect,
            1500,
          );
        };
      };

      connect();

      return () => {
        stopped = true;

        if (reconnectTimer) {
          clearTimeout(
            reconnectTimer,
          );
        }

        socket?.close();
      };
    },
    [applyFleet],
  );


  useEffect(
    () => {
      let stopped = false;

      const poll = async () => {
        const ids = (
          fleet.vehicles
          || []
        ).map(
          (vehicle) => (
            vehicle.vehicle_id
          ),
        );

        const entries = await Promise.all(
          ids.map(
            async (vehicleId) => {
              try {
                const state = await apiJson(
                  `/api/v1/vehicles/${
                    encodeURIComponent(
                      vehicleId,
                    )
                  }/control-state`,
                );

                return [
                  vehicleId,
                  state,
                ];
              } catch {
                return [
                  vehicleId,
                  null,
                ];
              }
            },
          ),
        );

        if (stopped) {
          return;
        }

        setControlStates(
          (previous) => {
            const next = {
              ...previous,
            };

            for (
              const [
                vehicleId,
                state,
              ]
              of entries
            ) {
              if (state) {
                next[
                  vehicleId
                ] = state;
              }
            }

            return next;
          },
        );
      };

      poll();

      const timer = setInterval(
        poll,
        1000,
      );

      return () => {
        stopped = true;

        clearInterval(
          timer,
        );
      };
    },
    [fleet.vehicles],
  );


  const controlReady = useMemo(
    () => {
      const profiles = (
        controlStatus?.profiles
        || []
      );

      return Boolean(
        controlStatus?.enabled
        && controlStatus?.started
        && profiles.length === 3
        && profiles.every(
          (item) => (
            item.connected
          ),
        )
      );
    },
    [controlStatus],
  );


  const liveReady = useMemo(
    () => {
      const profiles = (
        mqttLive?.profiles
        || []
      );

      return Boolean(
        mqttLive?.enabled
        && mqttLive?.started
        && profiles.length === 3
        && profiles.every(
          (item) => (
            item.connected
          ),
        )
      );
    },
    [mqttLive],
  );


  const switchProfile = useCallback(
    async (
      vehicle,
      targetProfile,
    ) => {
      const vehicleId = (
        vehicle.vehicle_id
      );

      setToast({
        type: "info",
        message:
          `${vehicleId}: requesting `
          + `${vehicle.security_profile}`
          + ` → ${targetProfile}`,
      });

      try {
        const initial = await apiJson(
          `/api/v1/vehicles/${
            encodeURIComponent(
              vehicleId,
            )
          }/security-profile`,
          {
            method: "POST",
            body: JSON.stringify({
              profile:
                targetProfile,
            }),
          },
        );

        setControlStates(
          (previous) => ({
            ...previous,
            [vehicleId]:
              initial,
          }),
        );

        for (
          let attempt = 0;
          attempt < 42;
          attempt += 1
        ) {
          await sleep(750);

          const state = await apiJson(
            `/api/v1/vehicles/${
              encodeURIComponent(
                vehicleId,
              )
            }/control-state`,
          );

          setControlStates(
            (previous) => ({
              ...previous,
              [vehicleId]:
                state,
            }),
          );

          const request = (
            state.request
            || {}
          );

          if (
            request.phase
            === "verified"
            && state.actual_profile
            === targetProfile
          ) {
            setToast({
              type: "success",
              message:
                `${vehicleId}: `
                + `${targetProfile} VERIFIED`,
            });

            await refreshSystem();

            return;
          }

          if (
            request.phase
            === "failed"
            || request.phase
            === "timeout"
          ) {
            throw new Error(
              request.error
              || `profile switch ${
                request.phase
              }`,
            );
          }
        }

        throw new Error(
          "verification timed out",
        );
      } catch (error) {
        setToast({
          type: "error",
          message:
            `${vehicleId}: ${
              error.message
            }`,
        });
      }
    },
    [refreshSystem],
  );


  const allEvents = useMemo(
    () => (
      Object.values(
        controlStates,
      )
        .flatMap(
          (state) => (
            state?.recent_events
            || []
          ),
        )
        .sort(
          (a, b) => (
            new Date(
              b.timestamp_utc,
            ).getTime()
            - new Date(
              a.timestamp_utc,
            ).getTime()
          ),
        )
    ),
    [controlStates],
  );


  const selectedVehicle = useMemo(
    () => (
      fleet.vehicles.find(
        (vehicle) => (
          vehicle.vehicle_id
          === selectedVehicleId
        ),
      )
      || null
    ),
    [
      fleet.vehicles,
      selectedVehicleId,
    ],
  );


  const liveConnectedCount = (
    mqttLive?.profiles
    || []
  ).filter(
    (item) => item.connected,
  ).length;

  const controlConnectedCount = (
    controlStatus?.profiles
    || []
  ).filter(
    (item) => item.connected,
  ).length;


  return (
    <div
      className={
        `dashboard-shell ${
          demoMode
            ? "demo-mode"
            : ""
        }`
      }
    >
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            OCC
          </div>

          <div>
            <div className="eyebrow">
              CYBERSECURITY PLATFORM
            </div>

            <h1>
              Operations Control Center
            </h1>
          </div>
        </div>

        <div className="topbar-actions">
          <button
            className={
              `demo-button ${
                demoMode
                  ? "active"
                  : ""
              }`
            }
            onClick={() => setDemoMode(
              (value) => !value,
            )}
          >
            ◉ Demo
          </button>

          <ThemeSwitcher
            value={theme}
            onChange={setTheme}
          />
        </div>
      </header>

      <main className="dashboard-main">
        <section className="system-strip">
          <StatusPill
            ok={
              health?.status
              === "ok"
            }
            label="OCC API"
            helper={
              health?.status
              || "waiting"
            }
          />

          <StatusPill
            ok={
              wsState
              === "connected"
            }
            label="Live stream"
            helper={wsState}
          />

          <StatusPill
            ok={liveReady}
            label="MQTT observer"
            helper={
              `${liveConnectedCount}/3 profiles`
            }
          />

          <StatusPill
            ok={controlReady}
            label="Control plane"
            helper={
              `${controlConnectedCount}/3 profiles`
            }
          />

          <StatusPill
            ok={
              fleet.online_count
              > 0
            }
            label="Fleet"
            helper={
              `${fleet.online_count}/${
                fleet.vehicle_count
              } online`
            }
          />
        </section>

        <section className="protocol-tabs">
          <button className="protocol-tab active">
            <span className="protocol-dot" />
            MQTT
          </button>

          <button
            className="protocol-tab disabled"
            disabled
            title="OPC UA is not yet integrated into the final operational dashboard"
          >
            OPC UA
            <small>
              pending
            </small>
          </button>

          <button
            className="protocol-tab disabled"
            disabled
            title="DDS is not yet integrated into the final operational dashboard"
          >
            DDS
            <small>
              pending
            </small>
          </button>

          <div className="protocol-spacer" />

          <div className="attack-placeholder">
            Attack lab
            <span>
              Phase 8 · not armed
            </span>
          </div>
        </section>

        <section className="hero">
          <div>
            <div className="eyebrow">
              LIVE MQTT OPERATIONS
            </div>

            <h2>
              Security-aware fleet control
            </h2>

            <p>
              Select a real vehicle security
              profile. The dashboard only marks
              a switch verified after status or
              telemetry confirms the actual
              ESP32 transition.
            </p>
          </div>

          <div className="hero-stats">
            <div>
              <span>Vehicles</span>
              <strong>
                {fleet.vehicle_count}
              </strong>
            </div>

            <div>
              <span>Online</span>
              <strong>
                {fleet.online_count}
              </strong>
            </div>

            <div>
              <span>Profiles</span>
              <strong>
                3
              </strong>
            </div>
          </div>
        </section>

        <section className="fleet-section">
          <div className="section-heading">
            <div>
              <div className="eyebrow">
                LIVE FLEET
              </div>

              <h2>
                Connected vehicles
              </h2>
            </div>

            {!controlReady && (
              <div className="warning-chip">
                Control unavailable
              </div>
            )}
          </div>

          <div className="vehicle-grid">
            {!fleet.vehicles.length && (
              <div className="empty-state large">
                Waiting for operational MQTT
                vehicles...
              </div>
            )}

            {fleet.vehicles.map(
              (vehicle) => (
                <VehicleCard
                  key={
                    vehicle.vehicle_id
                  }
                  vehicle={vehicle}
                  controlState={
                    controlStates[
                      vehicle.vehicle_id
                    ]
                  }
                  controlReady={
                    controlReady
                  }
                  history={
                    histories[
                      vehicle.vehicle_id
                    ]
                    || []
                  }
                  onSwitch={
                    switchProfile
                  }
                  onOpen={
                    setSelectedVehicleId
                  }
                />
              ),
            )}
          </div>
        </section>

        <div className="dashboard-two-column">
          <Topology
            vehicles={
              fleet.vehicles
            }
            mqttLive={mqttLive}
          />

          <EventTimeline
            events={allEvents}
          />
        </div>

        <section className="panel security-matrix">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">
                SECURITY LEVELS
              </div>

              <h2>
                MQTT protection model
              </h2>
            </div>
          </div>

          <div className="security-level-grid">
            {PROFILES.map(
              (profile) => (
                <div
                  className="security-level"
                  key={profile}
                >
                  <ProfileBadge
                    profile={profile}
                  />

                  <strong>
                    {
                      PROFILE_INFO[
                        profile
                      ].name
                    }
                  </strong>

                  <span>
                    {
                      PROFILE_INFO[
                        profile
                      ].description
                    }
                  </span>
                </div>
              ),
            )}
          </div>
        </section>

        <QualificationPanel
          qualification={
            qualification
          }
        />

        <footer>
          <span>
            OCC Cybersecurity Protocol
            Evaluation
          </span>

          <span>
            Operational dashboard · FAIR
            benchmark remains isolated
          </span>
        </footer>
      </main>

      <VehicleDrawer
        vehicle={selectedVehicle}
        controlState={
          selectedVehicleId
            ? controlStates[
                selectedVehicleId
              ]
            : null
        }
        onClose={
          () => setSelectedVehicleId(
            null,
          )
        }
      />

      {toast && (
        <div
          className={
            `toast ${toast.type}`
          }
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}

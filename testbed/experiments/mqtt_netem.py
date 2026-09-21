#!/usr/bin/env python3
"""Explicit, verified NetEm control for the MQTT proxy path."""

import subprocess

PROXY_CONTAINER = "testbed-netem-proxy"
INTERFACE = "eth0"

PROFILES = {
    "NET-ideal": (None, []),
    "NET-proxy-ideal": (None, []),
    "NET-delay": (["delay", "25ms"], ["delay 25ms"]),
    "NET-jitter": (
        ["delay", "25ms", "10ms", "distribution", "normal"],
        ["delay 25ms 10ms"],
    ),
    "NET-loss": (["loss", "2%"], ["loss 2%"]),
}


def _tc(*arguments, check=True):
    return subprocess.run(
        ["docker", "exec", PROXY_CONTAINER, "tc", *arguments],
        capture_output=True,
        text=True,
        check=check,
    )


def proxy_running():
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", PROXY_CONTAINER],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def reset_netem():
    if proxy_running():
        _tc("qdisc", "del", "dev", INTERFACE, "root", check=False)


def qdisc_state(with_stats=False):
    args = []
    if with_stats:
        args.append("-s")
    args.extend(["qdisc", "show", "dev", INTERFACE])
    return _tc(*args).stdout.strip()


def state_matches(net_profile, state):
    if net_profile == "NET-ideal":
        return True

    _, tokens = PROFILES[net_profile]
    normalized = " ".join(state.split())

    if not tokens:
        return "netem" not in normalized

    return (
        "netem" in normalized
        and all(token in normalized for token in tokens)
    )


def configure_netem(net_profile):
    if net_profile not in PROFILES:
        raise ValueError(
            f"Unknown MQTT network profile {net_profile!r}"
        )

    netem_args, _ = PROFILES[net_profile]

    if net_profile == "NET-ideal":
        reset_netem()
        return "not applicable: direct broker path"

    if not proxy_running():
        raise RuntimeError(f"{PROXY_CONTAINER} is not running")

    _tc("qdisc", "del", "dev", INTERFACE, "root", check=False)

    if netem_args is not None:
        _tc(
            "qdisc",
            "replace",
            "dev",
            INTERFACE,
            "root",
            "netem",
            *netem_args,
        )

    state = qdisc_state()

    if not state_matches(net_profile, state):
        raise RuntimeError(
            f"NetEm verification failed for {net_profile}: {state!r}"
        )

    return state


def write_netem_log(
    path,
    run_id,
    net_profile,
    started,
    ended,
    run_status,
    verified_before,
    verified_after,
    state_before,
    state_after,
):
    netem_args, _ = PROFILES[net_profile]

    lines = [
        f"run_id={run_id}",
        f"net_profile={net_profile}",
        f"netem_args={' '.join(netem_args) if netem_args else 'none'}",
        f"started_utc={started}",
        f"ended_utc={ended}",
        f"run_status={run_status}",
        f"netem_verified_before={str(verified_before).lower()}",
        f"netem_verified_after={str(verified_after).lower()}",
        "--- tc qdisc show dev eth0 (before run) ---",
        state_before,
        "--- tc -s qdisc show dev eth0 (after run, before reset) ---",
        state_after,
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")

#!/usr/bin/env python3

import argparse
import datetime
import getpass
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve()
REPO = HERE.parents[3]

FORMAL_ROOT = (
    REPO
    / "testbed"
    / "hardware"
    / "esp32"
    / "mqtt"
    / "formal"
)

PI_ECHO = (
    REPO
    / "testbed"
    / "hardware"
    / "raspberrypi"
    / "mqtt"
    / "formal"
    / "fair_mqtt_echo.py"
)

RESULT_ROOT = (
    REPO
    / "testbed"
    / "results"
    / "fair_v1"
    / "mqtt"
)

DEFAULT_CONFIG = (
    Path.home()
    / ".config"
    / "occ-fair-v1"
    / "mqtt-formal.json"
)

BROKER_PORTS = {
    "C0": 1883,
    "C1": 1884,
    "C2": 8883,
}


def command(args, **kwargs):
    printable = " ".join(
        shlex.quote(str(x))
        for x in args
    )

    print(f"+ {printable}", flush=True)

    return subprocess.run(
        [str(x) for x in args],
        check=True,
        **kwargs,
    )


def output(args):
    return subprocess.check_output(
        [str(x) for x in args],
        text=True,
    ).strip()


def remote(pi, shell_command, tty=False):
    ssh = ["ssh"]

    if tty:
        ssh.append("-tt")

    ssh.extend(
        [
            pi,
            shell_command,
        ]
    )

    return command(ssh)


def git_commit():
    return output(
        [
            "git",
            "-C",
            REPO,
            "rev-parse",
            "HEAD",
        ]
    )


def require_clean_repository():
    dirty = output(
        [
            "git",
            "-C",
            REPO,
            "status",
            "--porcelain",
        ]
    )

    if dirty:
        raise SystemExit(
            "Repository is not clean.\n"
            "Formal runs require a committed "
            "implementation.\n\n"
            + dirty
        )


def prompt(
    label,
    *,
    secret=False,
    default=None,
):
    suffix = ""

    if default is not None:
        suffix = f" [{default}]"

    text = f"{label}{suffix}: "

    value = (
        getpass.getpass(text)
        if secret
        else input(text)
    )

    if not value and default is not None:
        value = default

    if not value:
        raise SystemExit(
            f"{label} cannot be empty"
        )

    return value


def init_config(path):
    print()
    print(
        "Create local FAIR-V1 MQTT configuration."
    )
    print(
        "This file contains secrets and stays "
        "outside the repository."
    )
    print()
    print(
        "IMPORTANT: use ONE common workload for "
        "MQTT, OPC UA and DDS."
    )
    print(
        "Do not change workload values between "
        "security profiles/repeats."
    )
    print()

    config = {
        "wifi_ssid": prompt(
            "Benchmark Wi-Fi SSID"
        ),
        "wifi_password": prompt(
            "Benchmark Wi-Fi password",
            secret=True,
        ),
        "broker_host": prompt(
            "OCC MQTT hostname",
            default="occ-pi.local",
        ),
        "mqtt_username": prompt(
            "MQTT benchmark username",
            default="occuser",
        ),
        "mqtt_password": prompt(
            "MQTT benchmark password",
            secret=True,
        ),
        "sntp_server": prompt(
            "SNTP server for C2"
        ),
        "workload": {
            "speed": prompt(
                "Common workload speed"
            ),
            "pos_x": prompt(
                "Common workload pos_x"
            ),
            "pos_y": prompt(
                "Common workload pos_y"
            ),
            "heading": prompt(
                "Common workload heading"
            ),
            "battery_pct": prompt(
                "Common workload battery_pct"
            ),
            "state": prompt(
                "Common workload state"
            ),
        },
    }

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            config,
            indent=2,
        )
        + "\n"
    )

    path.chmod(0o600)

    print()
    print(
        f"Protected config written to: {path}"
    )
    print(
        "Permissions: 0600"
    )


def load_config(path):
    if not path.is_file():
        raise SystemExit(
            f"Config not found: {path}\n"
            "Run the init command first."
        )

    config = json.loads(
        path.read_text()
    )

    required = (
        "wifi_ssid",
        "wifi_password",
        "broker_host",
        "mqtt_username",
        "mqtt_password",
        "sntp_server",
        "workload",
    )

    missing = [
        key
        for key in required
        if not config.get(key)
    ]

    if missing:
        raise SystemExit(
            "Config missing: "
            + ", ".join(missing)
        )

    workload = config["workload"]

    workload_keys = (
        "speed",
        "pos_x",
        "pos_y",
        "heading",
        "battery_pct",
        "state",
    )

    missing_workload = [
        key
        for key in workload_keys
        if workload.get(key) in (
            None,
            "",
        )
    ]

    if missing_workload:
        raise SystemExit(
            "Workload config missing: "
            + ", ".join(
                missing_workload
            )
        )

    return config


def kconfig_string(value):
    value = str(value)

    value = value.replace(
        "\\",
        "\\\\",
    )

    value = value.replace(
        '"',
        '\\"',
    )

    return f'"{value}"'


def write_sdkconfig_defaults(
    path,
    *,
    profile,
    repeat,
    run_id,
    config,
):
    port = BROKER_PORTS[profile]

    scheme = (
        "mqtts"
        if profile == "C2"
        else "mqtt"
    )

    broker_uri = (
        f"{scheme}://"
        f"{config['broker_host']}:"
        f"{port}"
    )

    if profile == "C0":
        username = ""
        password = ""
    else:
        username = (
            config["mqtt_username"]
        )
        password = (
            config["mqtt_password"]
        )

    sntp = (
        config["sntp_server"]
        if profile == "C2"
        else ""
    )

    workload = config["workload"]

    values = {
        "CONFIG_FAIR_WIFI_SSID":
            config["wifi_ssid"],
        "CONFIG_FAIR_WIFI_PASSWORD":
            config["wifi_password"],
        "CONFIG_FAIR_SNTP_SERVER":
            sntp,
        "CONFIG_FAIR_MQTT_BROKER_URI":
            broker_uri,
        "CONFIG_FAIR_MQTT_USERNAME":
            username,
        "CONFIG_FAIR_MQTT_PASSWORD":
            password,
        "CONFIG_FAIR_MQTT_CA_CERT_PEM":
            "",
        "CONFIG_FAIR_RUN_ID":
            run_id,
        "CONFIG_FAIR_WORKLOAD_SPEED":
            workload["speed"],
        "CONFIG_FAIR_WORKLOAD_POS_X":
            workload["pos_x"],
        "CONFIG_FAIR_WORKLOAD_POS_Y":
            workload["pos_y"],
        "CONFIG_FAIR_WORKLOAD_HEADING":
            workload["heading"],
        "CONFIG_FAIR_WORKLOAD_BATTERY_PCT":
            workload["battery_pct"],
        "CONFIG_FAIR_WORKLOAD_STATE":
            workload["state"],
    }

    lines = []

    for key, value in values.items():
        lines.append(
            f"{key}="
            f"{kconfig_string(value)}"
        )

    lines.append(
        "CONFIG_FAIR_REPEAT_INDEX="
        f"{repeat}"
    )

    path.write_text(
        "\n".join(lines)
        + "\n"
    )


def capture_serial(
    port,
    *,
    complete_log,
    raw_log,
    timeout_seconds=150,
):
    try:
        import serial
    except ImportError as exc:
        raise SystemExit(
            "pyserial is unavailable. "
            "Run this tool with the "
            "ESP-IDF Python environment."
        ) from exc

    raw_count = 0
    summary = None

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0.5

    # Avoid deliberately restarting the
    # ESP32 after the flash-triggered boot.
    ser.dtr = False
    ser.rts = False

    ser.open()

    try:
        deadline = (
            time.time()
            + timeout_seconds
        )

        with (
            complete_log.open(
                "x",
                encoding="utf-8",
            ) as full,
            raw_log.open(
                "x",
                encoding="utf-8",
            ) as raw,
        ):
            while time.time() < deadline:
                line = (
                    ser.readline()
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                    .rstrip()
                )

                if not line:
                    continue

                print(line)

                full.write(
                    line + "\n"
                )
                full.flush()

                if "FAIR_RAW|" in line:
                    raw.write(
                        line + "\n"
                    )
                    raw.flush()
                    raw_count += 1

                if "FAIR_SUMMARY|" in line:
                    summary = line
                    break
    finally:
        ser.close()

    return raw_count, summary


def stop_remote_echo(
    pi,
    *,
    pid_file,
):
    script = f"""
if [ -f {shlex.quote(pid_file)} ]; then
    pid="$(cat {shlex.quote(pid_file)})"
    kill "$pid" 2>/dev/null || true
fi
"""

    remote(
        pi,
        "sudo bash -lc "
        + shlex.quote(script),
        tty=True,
    )


def restore_operational_occ(pi):
    remote(
        pi,
        "sudo systemctl restart occ-mqtt "
        "&& sudo systemctl is-active occ-mqtt",
        tty=True,
    )


def run_formal(args):
    if args.repeat < 1 or args.repeat > 5:
        raise SystemExit(
            "Formal repeat must be 1..5"
        )

    if shutil.which("idf.py") is None:
        raise SystemExit(
            "idf.py not found. "
            "Source ESP-IDF export.sh first."
        )

    require_clean_repository()

    config = load_config(
        args.config.expanduser()
    )

    commit = git_commit()

    now = (
        datetime.datetime.now(
            datetime.timezone.utc
        )
        .strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )

    run_id = (
        f"MQTT-{args.profile}"
        f"-R{args.repeat}"
        f"-{now}"
        f"-{commit[:7]}"
    )

    run_dir = (
        RESULT_ROOT
        / run_id
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    profile_lower = (
        args.profile.lower()
    )

    project = (
        FORMAL_ROOT
        / profile_lower
        / "vehicle1"
    )

    if not project.is_dir():
        raise SystemExit(
            f"Formal project missing: "
            f"{project}"
        )

    print()
    print(
        "===== FAIR-V1 MQTT FORMAL RUN ====="
    )
    print(f"run_id={run_id}")
    print(
        f"profile={args.profile}"
    )
    print(
        f"repeat={args.repeat}"
    )
    print(
        f"git_commit={commit}"
    )
    print(
        f"serial_port={args.port}"
    )
    print(
        f"results={run_dir}"
    )
    print()

    remote_echo = (
        f"/tmp/"
        f"fair_mqtt_echo_{run_id}.py"
    )

    remote_events = (
        f"/tmp/"
        f"{run_id}.occ_events.jsonl"
    )

    remote_service_log = (
        f"/tmp/"
        f"{run_id}.occ_service.log"
    )

    remote_pid = (
        f"/tmp/"
        f"{run_id}.occ_echo.pid"
    )

    remote_started = False
    operational_stopped = False

    try:
        with tempfile.TemporaryDirectory(
            prefix="fair-v1-mqtt-"
        ) as temporary:
            defaults = (
                Path(temporary)
                / "sdkconfig.defaults"
            )

            write_sdkconfig_defaults(
                defaults,
                profile=args.profile,
                repeat=args.repeat,
                run_id=run_id,
                config=config,
            )

            # Force the new run ID/repeat to
            # become the generated sdkconfig.
            for name in (
                "sdkconfig",
                "sdkconfig.old",
            ):
                candidate = (
                    project / name
                )

                if candidate.exists():
                    candidate.unlink()

            command(
                [
                    "idf.py",
                    "-C",
                    project,
                    "-D",
                    "SDKCONFIG_DEFAULTS="
                    + str(defaults),
                    "reconfigure",
                    "build",
                ]
            )

            print()
            print(
                "===== PI PRE-FLIGHT ====="
            )

            remote(
                args.pi,
                "systemctl is-active "
                "--quiet mosquitto",
            )

            stale = subprocess.run(
                [
                    "ssh",
                    args.pi,
                    "pgrep -af "
                    "'[f]air_mqtt_echo.py'",
                ],
                text=True,
                capture_output=True,
            )

            if stale.returncode == 0:
                raise SystemExit(
                    "A FAIR MQTT echo process "
                    "is already running on Pi:\n"
                    + stale.stdout
                )

            remote(
                args.pi,
                "sudo systemctl stop "
                "occ-mqtt",
                tty=True,
            )

            operational_stopped = True

            print()
            print(
                "===== START FORMAL PI ECHO ====="
            )

            command(
                [
                    "scp",
                    PI_ECHO,
                    f"{args.pi}:"
                    f"{remote_echo}",
                ]
            )

            broker_port = (
                BROKER_PORTS[
                    args.profile
                ]
            )

            auth_args = ""

            if args.profile in (
                "C1",
                "C2",
            ):
                auth_args = (
                    ' --username '
                    '"$OCC_MQTT_USERNAME"'
                    ' --password-env '
                    'OCC_MQTT_PASSWORD'
                )

            tls_args = ""

            if args.profile == "C2":
                tls_args = (
                    ' --ca-cert '
                    '"$OCC_MQTT_CA_FILE"'
                )

            service_id = (
                f"mqtt-"
                f"{profile_lower}-"
                f"r{args.repeat}-"
                f"{now}"
            )

            inner = f"""
set -e
set -a
source /etc/occ-final-runtime/mqtt.env
set +a

nohup /opt/occ-final-runtime/.venv/bin/python \
    {shlex.quote(remote_echo)} \
    --profile {shlex.quote(args.profile)} \
    --broker-host {shlex.quote(config["broker_host"])} \
    --broker-port {broker_port} \
    {auth_args} \
    {tls_args} \
    --run-id {shlex.quote(run_id)} \
    --clock-domain pi_monotonic \
    --service-id {shlex.quote(service_id)} \
    --event-log {shlex.quote(remote_events)} \
    > {shlex.quote(remote_service_log)} 2>&1 &

echo $! > {shlex.quote(remote_pid)}
"""

            remote(
                args.pi,
                "sudo bash -lc "
                + shlex.quote(inner),
                tty=True,
            )

            remote_started = True

            time.sleep(2)

            check = f"""
pid="$(cat {shlex.quote(remote_pid)})"
kill -0 "$pid"
cat {shlex.quote(remote_service_log)}
"""

            remote(
                args.pi,
                "sudo bash -lc "
                + shlex.quote(check),
                tty=True,
            )

            print()
            print(
                "===== FLASH VM-001 ====="
            )

            command(
                [
                    "idf.py",
                    "-C",
                    project,
                    "-p",
                    args.port,
                    "flash",
                ]
            )

            print()
            print(
                "===== CAPTURE FORMAL RUN ====="
            )

            raw_count, summary = (
                capture_serial(
                    args.port,
                    complete_log=(
                        run_dir
                        / "esp32_serial.log"
                    ),
                    raw_log=(
                        run_dir
                        / "vehicle_raw.log"
                    ),
                )
            )

            print()
            print(
                "===== RETRIEVE PI EVENTS ====="
            )

            stop_remote_echo(
                args.pi,
                pid_file=remote_pid,
            )

            remote_started = False

            for remote_path, local_name in (
                (
                    remote_events,
                    "occ_events.jsonl",
                ),
                (
                    remote_service_log,
                    "occ_service.log",
                ),
            ):
                subprocess.run(
                    [
                        "scp",
                        f"{args.pi}:"
                        f"{remote_path}",
                        run_dir
                        / local_name,
                    ],
                    check=False,
                )

            status = {
                "run_id": run_id,
                "protocol": "MQTT",
                "security_profile":
                    args.profile,
                "repeat_number":
                    args.repeat,
                "firmware_git_hash":
                    commit,
                "vehicle":
                    "VM-001",
                "raw_row_count":
                    raw_count,
                "summary_seen":
                    summary is not None,
                "summary_line":
                    summary,
                "runner_capture_complete":
                    (
                        raw_count == 600
                        and summary is not None
                    ),
            }

            (
                run_dir
                / "runner_status.json"
            ).write_text(
                json.dumps(
                    status,
                    indent=2,
                )
                + "\n"
            )

            print()
            print(
                "===== GROUP-2 CAPTURE CHECK ====="
            )
            print(
                f"FAIR_RAW rows: {raw_count}"
            )
            print(
                "FAIR_SUMMARY: "
                + (
                    "present"
                    if summary
                    else "MISSING"
                )
            )

            if (
                raw_count != 600
                or summary is None
            ):
                raise SystemExit(
                    "Formal capture incomplete. "
                    "Run preserved for later "
                    "INVALID classification."
                )

            print()
            print(
                "FORMAL CAPTURE COMPLETE"
            )
            print(
                f"Results: {run_dir}"
            )

    finally:
        if remote_started:
            try:
                stop_remote_echo(
                    args.pi,
                    pid_file=remote_pid,
                )
            except Exception:
                pass

        if operational_stopped:
            try:
                restore_operational_occ(
                    args.pi
                )
            except Exception:
                print(
                    "WARNING: failed to restart "
                    "occ-mqtt automatically",
                    file=sys.stderr,
                )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "FAIR-V1 formal MQTT "
            "benchmark orchestrator"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    init = sub.add_parser(
        "init",
        help=(
            "create protected local "
            "benchmark configuration"
        ),
    )

    init.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    run = sub.add_parser(
        "run",
        help=(
            "execute one formal MQTT "
            "repeat"
        ),
    )

    run.add_argument(
        "profile",
        choices=(
            "C0",
            "C1",
            "C2",
        ),
    )

    run.add_argument(
        "repeat",
        type=int,
    )

    run.add_argument(
        "--port",
        default=
            "/dev/cu.usbserial-0001",
    )

    run.add_argument(
        "--pi",
        default=
            "moulikha@occ-pi.local",
    )

    run.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    args = parser.parse_args()

    if args.command == "init":
        init_config(
            args.config.expanduser()
        )
        return

    run_formal(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve()
REPO = HERE.parents[3]

SCHEMA = (
    REPO
    / "testbed"
    / "docs"
    / "fair_v1"
    / "schemas"
    / "fair_v1_run_metadata.schema.json"
)

FAIR_ECHO = (
    REPO
    / "testbed"
    / "hardware"
    / "raspberrypi"
    / "mqtt"
    / "formal"
    / "fair_mqtt_echo.py"
)

FORMAL_ROOT = (
    REPO
    / "testbed"
    / "hardware"
    / "esp32"
    / "mqtt"
    / "formal"
)


def sha256_file(path):
    h = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def sha256_object(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def local_output(command):
    return subprocess.check_output(
        [str(x) for x in command],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def remote_output(pi, command):
    try:
        return subprocess.check_output(
            [
                "ssh",
                pi,
                command,
            ],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception:
        return "unavailable"


def parse_run_start_utc(run_id):
    match = re.search(
        r"-(\d{8}T\d{6}Z)-[0-9a-f]+$",
        run_id,
    )

    if not match:
        raise SystemExit(
            "Cannot derive UTC timestamp "
            "from run_id"
        )

    dt = datetime.datetime.strptime(
        match.group(1),
        "%Y%m%dT%H%M%SZ",
    ).replace(
        tzinfo=datetime.timezone.utc
    )

    return (
        dt.isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def parse_run_t0(serial_log):
    pattern = re.compile(
        r"FAIR run start t0=(\d+)"
    )

    for line in serial_log.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        match = pattern.search(line)

        if match:
            return int(
                match.group(1)
            )

    return None


def parse_achieved_rate(summary):
    if not summary:
        return None

    match = re.search(
        r"achieved_rate=([0-9.]+)",
        summary,
    )

    if not match:
        return None

    return float(
        match.group(1)
    )


def get_remote_facts(pi):
    facts = {}

    facts["mosquitto_version"] = (
        remote_output(
            pi,
            "mosquitto -h 2>&1 "
            "| head -n 1",
        )
    )

    facts["paho_version"] = (
        remote_output(
            pi,
            "/opt/occ-final-runtime/"
            ".venv/bin/python -c "
            "\"import importlib.metadata as m; "
            "print(m.version('paho-mqtt'))\"",
        )
    )

    facts["pi_environment"] = (
        remote_output(
            pi,
            ". /etc/os-release; "
            "printf '%s | ' \"$PRETTY_NAME\"; "
            "uname -srmo",
        )
    )

    broker_hash = remote_output(
        pi,
        "cat "
        "/etc/mosquitto/mosquitto.conf "
        "/etc/mosquitto/conf.d/*.conf "
        "2>/dev/null "
        "| sha256sum "
        "| awk '{print $1}'",
    )

    if re.fullmatch(
        r"[0-9a-fA-F]{64}",
        broker_hash,
    ):
        facts["broker_config_identity"] = (
            f"sha256:{broker_hash.lower()}"
        )
    else:
        facts["broker_config_identity"] = (
            "unavailable"
        )

    return facts


def validate_metadata(path):
    try:
        from jsonschema import (
            Draft202012Validator,
        )
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "jsonschema is required in the "
            "active Python environment."
        ) from exc

    schema = json.loads(
        SCHEMA.read_text(
            encoding="utf-8"
        )
    )

    metadata = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator(
        schema
    ).validate(
        metadata
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Finalize FAIR-V1 MQTT formal "
            "run metadata"
        )
    )

    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--config",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--pi",
        required=True,
    )

    args = parser.parse_args()

    run_dir = (
        args.run_dir
        .expanduser()
        .resolve()
    )

    config_path = (
        args.config
        .expanduser()
        .resolve()
    )

    status_path = (
        run_dir
        / "runner_status.json"
    )

    serial_path = (
        run_dir
        / "esp32_serial.log"
    )

    occ_events_path = (
        run_dir
        / "occ_events.jsonl"
    )

    if not status_path.is_file():
        raise SystemExit(
            f"Missing runner status: "
            f"{status_path}"
        )

    if not serial_path.is_file():
        raise SystemExit(
            f"Missing serial log: "
            f"{serial_path}"
        )

    if not config_path.is_file():
        raise SystemExit(
            f"Missing local config: "
            f"{config_path}"
        )

    status = json.loads(
        status_path.read_text()
    )

    config = json.loads(
        config_path.read_text()
    )

    run_id = status["run_id"]
    profile = status[
        "security_profile"
    ]
    repeat = int(
        status["repeat_number"]
    )
    commit = status[
        "firmware_git_hash"
    ]

    profile_lower = (
        profile.lower()
    )

    project = (
        FORMAL_ROOT
        / profile_lower
        / "vehicle1"
    )

    sdkconfig = (
        project
        / "sdkconfig"
    )

    app_binary = (
        project
        / "build"
        / (
            "fair_v1_mqtt_"
            f"{profile_lower}"
            "_vehicle1.bin"
        )
    )

    if not sdkconfig.is_file():
        raise SystemExit(
            f"Generated sdkconfig missing: "
            f"{sdkconfig}"
        )

    if not app_binary.is_file():
        raise SystemExit(
            f"Firmware binary missing: "
            f"{app_binary}"
        )

    run_t0 = parse_run_t0(
        serial_path
    )

    achieved_rate = (
        parse_achieved_rate(
            status.get(
                "summary_line"
            )
        )
    )

    invalidation_reasons = []
    flag_reasons = []

    run_start_utc = status.get(
        "run_start_utc"
    )

    if not run_start_utc:
        invalidation_reasons.append(
            "actual_run_start_utc_not_captured"
        )

        run_start_utc = (
            parse_run_start_utc(
                run_id
            )
        )

    if (
        status.get(
            "raw_row_count"
        )
        != 600
    ):
        invalidation_reasons.append(
            "vehicle_raw_row_count_not_600"
        )

    if not status.get(
        "summary_seen"
    ):
        invalidation_reasons.append(
            "fair_summary_missing"
        )

    if run_t0 is None:
        invalidation_reasons.append(
            "vehicle_run_t0_missing"
        )
        run_t0 = 0

    if (
        not occ_events_path.is_file()
        or occ_events_path.stat().st_size
        == 0
    ):
        invalidation_reasons.append(
            "occ_event_log_missing_or_empty"
        )

    remote = get_remote_facts(
        args.pi
    )

    if (
        remote[
            "mosquitto_version"
        ]
        == "unavailable"
    ):
        invalidation_reasons.append(
            "mosquitto_version_unavailable"
        )

    if (
        remote[
            "paho_version"
        ]
        == "unavailable"
    ):
        invalidation_reasons.append(
            "paho_version_unavailable"
        )

    if (
        remote[
            "pi_environment"
        ]
        == "unavailable"
    ):
        invalidation_reasons.append(
            "pi_environment_unavailable"
        )

    if (
        remote[
            "broker_config_identity"
        ]
        == "unavailable"
    ):
        invalidation_reasons.append(
            "mqtt_broker_config_identity_unavailable"
        )

    if invalidation_reasons:
        validity = "invalid"

    elif (
        achieved_rate is not None
        and achieved_rate < 0.95
    ):
        validity = "flagged"

        flag_reasons.append(
            "achieved_rate_below_95_percent"
        )

    elif achieved_rate is None:
        validity = "invalid"

        invalidation_reasons.append(
            "achieved_rate_unavailable"
        )

    else:
        validity = "valid"

    try:
        idf_version = local_output(
            [
                "idf.py",
                "--version",
            ]
        )
    except Exception:
        idf_version = (
            "ESP-IDF v5.5.5"
        )

    firmware_config_hash = (
        sha256_file(
            sdkconfig
        )
    )

    firmware_binary_hash = (
        sha256_file(
            app_binary
        )
    )

    echo_hash = (
        sha256_file(
            FAIR_ECHO
        )
    )

    topology_description = {
        "network_stage":
            "direct",
        "vehicle":
            "VM-001",
        "hardware_unit":
            "ESP32_1",
        "vehicle_mac":
            "94:3c:c6:33:6a:64",
        "occ_host":
            "occ-pi.local",
        "wifi_ssid":
            config["wifi_ssid"],
        "broker_host":
            config["broker_host"],
        "broker_port":
            {
                "C0": 1883,
                "C1": 1884,
                "C2": 8883,
            }[profile],
        "wireguard":
            False,
        "gateway":
            None,
    }

    topology_hash = (
        sha256_object(
            topology_description
        )
    )

    metadata = {
        "dataset_schema_version":
            "1.0",

        "run_id":
            run_id,

        "run_group_id":
            (
                "fair-v1-mqtt-"
                f"{profile_lower}"
                "-native-direct-vm001"
            ),

        "campaign_id":
            "fair-v1-vm001-native-baseline",

        "condition_id":
            (
                "mqtt-"
                f"{profile_lower}"
                "-native-direct"
            ),

        "repeat_index":
            repeat,

        "protocol":
            "mqtt",

        "security_profile":
            profile,

        "spec_version":
            "1.0",

        "spec_git_hash":
            commit,

        "payload_schema_version":
            "0.1",

        "run_start_utc":
            run_start_utc,

        # Frozen schema explicitly permits null.
        # ESP32 and Pi monotonic clocks are not
        # treated as synchronized clock domains.
        "occ_run_start_reference_us":
            None,

        "occ_clock_domain":
            "pi_monotonic",

        "active_vehicle_count":
            1,

        "concurrency_mode":
            "single_legitimate",

        "participating_serial_numbers":
            [
                "VM-001",
            ],

        "participating_hardware_unit_ids":
            [
                "ESP32_1",
            ],

        "attacker_present":
            False,

        "vehicle_instances":
            [
                {
                    "hardware_unit_id":
                        "ESP32_1",

                    "serialNumber":
                        "VM-001",

                    "vehicle_role":
                        "legitimate",

                    "board_model":
                        "ESP32",

                    "board_revision":
                        None,

                    "firmware_git_commit":
                        commit,

                    "firmware_build_config_identity":
                        (
                            "sha256:"
                            f"{firmware_config_hash}"
                        ),

                    "firmware_artifact_sha256":
                        firmware_binary_hash,

                    "protocol":
                        "mqtt",

                    "security_profile":
                        profile,

                    "run_t0_us":
                        run_t0,

                    "vehicle_clock_domain":
                        "esp32_1_monotonic",

                    "network_path_id":
                        "direct_path",

                    "clock_sync_to_occ":
                        {
                            "method":
                                "none",

                            "status":
                                "unsynchronized",

                            "offset_us":
                                None,

                            "uncertainty_us":
                                None,
                        },
                },
            ],

        "occ_deployment_mode":
            "native",

        "occ_services":
            [
                {
                    "service_id":
                        "mqtt_broker",

                    "service_name":
                        "mosquitto",

                    "service_role":
                        "mqtt_broker",

                    "version":
                        remote[
                            "mosquitto_version"
                        ],

                    "config_file_or_hash":
                        remote[
                            "broker_config_identity"
                        ],

                    "executable_or_runtime_identity":
                        "mosquitto",

                    "service_manager":
                        "systemd",

                    "service_unit":
                        "mosquitto.service",

                    "git_commit":
                        None,

                    "deployment_instance_ids":
                        [
                            "native:mosquitto",
                        ],
                },
                {
                    "service_id":
                        "fair_echo",

                    "service_name":
                        "fair_mqtt_echo",

                    "service_role":
                        "fair_application_echo",

                    "version":
                        f"git:{commit}",

                    "config_file_or_hash":
                        (
                            "sha256:"
                            f"{echo_hash}"
                        ),

                    "executable_or_runtime_identity":
                        (
                            "/opt/occ-final-runtime/"
                            ".venv/bin/python"
                        ),

                    "service_manager":
                        "manual",

                    "service_unit":
                        None,

                    "git_commit":
                        commit,

                    "deployment_instance_ids":
                        [
                            "native:fair_echo",
                        ],
                },
            ],

        "middleware_mode":
            "native",

        "middleware_service_id":
            None,

        "network_stage":
            "direct",

        "network_topology_id":
            "direct-v1",

        "network_topology_config_hash":
            topology_hash,

        "routing_config_hash":
            None,

        "network_segments":
            [
                {
                    "segment_id":
                        "direct_segment",

                    "segment_role":
                        "vehicle_occ",

                    "interface_class":
                        "wifi",

                    "addressing_identity":
                        (
                            "ssid="
                            f"{config['wifi_ssid']}"
                        ),
                },
            ],

        "network_interfaces":
            [
                {
                    "interface_id":
                        "esp32_1_wifi",

                    "owner_id":
                        "ESP32_1",

                    "interface_name":
                        "wifi",

                    "segment_id":
                        "direct_segment",

                    "interface_role":
                        "vehicle",
                },
                {
                    "interface_id":
                        "pi_wlan0",

                    "owner_id":
                        "PI5_OCC",

                    "interface_name":
                        "wlan0",

                    "segment_id":
                        "direct_segment",

                    "interface_role":
                        "occ",
                },
            ],

        "gateway_instances":
            [],

        "network_paths":
            [
                {
                    "network_path_id":
                        "direct_path",

                    "source_endpoint_id":
                        "ESP32_1",

                    "destination_endpoint_id":
                        "PI5_OCC",

                    "gateway_ids":
                        [],

                    "path_config_hash":
                        topology_hash,
                },
            ],

        "wireguard":
            {
                "enabled":
                    False,

                "version":
                    None,

                "interface_name":
                    None,

                "interface_id":
                    None,

                "peer_identity":
                    None,

                "peer_public_key_fingerprint":
                    None,

                "config_hash":
                    None,

                "tunnel_state_at_run_start":
                    "not_applicable",

                "mtu":
                    None,

                "endpoint_role":
                    None,
            },

        "attack_scenarios":
            [],

        "docker_deployment":
            None,

        "container_instances":
            [],

        "k3s_deployment":
            None,

        "k3s_workloads":
            [],

        "run_validity_status":
            validity,

        "flag_reasons":
            flag_reasons,

        "invalidation_reasons":
            invalidation_reasons,

        "reproducibility":
            {
                "esp_idf_version":
                    idf_version,

                "firmware_git_commit":
                    commit,

                "firmware_build_configuration_identity":
                    (
                        "sha256:"
                        f"{firmware_config_hash}"
                    ),

                "protocol_library_version":
                    (
                        "ESP-MQTT bundled with "
                        f"{idf_version}; "
                        "paho-mqtt "
                        f"{remote['paho_version']}"
                    ),

                "raspberry_pi_software_version":
                    (
                        "fair_mqtt_echo.py "
                        f"git={commit} "
                        "sha256="
                        f"{echo_hash}"
                    ),

                "raspberry_pi_os_environment":
                    remote[
                        "pi_environment"
                    ],
            },

        "active_attacker_count":
            0,
    }

    metadata_path = (
        run_dir
        / "run_metadata.json"
    )

    metadata_path.write_text(
        json.dumps(
            metadata,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    validate_metadata(
        metadata_path
    )

    status[
        "metadata_schema_valid"
    ] = True

    status[
        "run_validity_status"
    ] = validity

    status[
        "flag_reasons"
    ] = flag_reasons

    status[
        "invalidation_reasons"
    ] = invalidation_reasons

    status_path.write_text(
        json.dumps(
            status,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(
        "Metadata schema: VALID"
    )
    print(
        f"Run validity: {validity}"
    )
    print(
        f"Metadata: {metadata_path}"
    )


if __name__ == "__main__":
    main()

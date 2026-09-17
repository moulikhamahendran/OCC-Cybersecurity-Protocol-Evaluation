#!/usr/bin/env python3

import csv
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_DIR = Path(__file__).resolve().parents[2]
TESTBED_DIR = PROJECT_DIR / "testbed"

SECURITY_DIR = TESTBED_DIR / "config" / "dds" / "security"
CONTAINER_CONFIG_DIR = SECURITY_DIR / "container"
RESULTS_ROOT = (
    TESTBED_DIR / "results" / "dds" / "security_controls"
)

IMAGE = "occ-dds-security:11.0.1"
CONTAINER_ROOT = "/workspace"

PUBLISHER_PROGRAM = (
    "testbed/protocols/dds/dds_publisher.py"
)
SUBSCRIBER_PROGRAM = (
    "testbed/protocols/dds/dds_subscriber.py"
)


def run(command, *, check=True):
    return subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=check,
        text=True,
        capture_output=True,
    )


def docker(*arguments, check=True):
    return run(
        ["docker", *arguments],
        check=check,
    )


def container_path(path):
    relative = path.resolve().relative_to(
        PROJECT_DIR.resolve()
    )
    return f"{CONTAINER_ROOT}/{relative.as_posix()}"


def security_uri(path):
    return f"file://{container_path(path)}"


def cleanup(container_names, network_name):
    for container_name in container_names:
        docker(
            "rm",
            "-f",
            container_name,
            check=False,
        )

    docker(
        "network",
        "rm",
        network_name,
        check=False,
    )


def wait_container(container_name):
    result = docker("wait", container_name)
    output = result.stdout.strip()

    if not output:
        raise RuntimeError(
            f"No exit status returned for {container_name}"
        )

    return int(output.splitlines()[-1])


def container_logs(container_name):
    result = docker(
        "logs",
        container_name,
        check=False,
    )
    return result.stdout + result.stderr


def replace_config(source, destination, replacements):
    config = source.read_text(encoding="utf-8")

    for old, new in replacements.items():
        if old not in config:
            raise RuntimeError(
                f"Configuration value not found: {old}"
            )
        config = config.replace(old, new)

    destination.write_text(
        config,
        encoding="utf-8",
    )


def docker_environment(
    security_level,
    net_profile,
    run_id,
    config_path=None,
):
    arguments = [
        "-e",
        f"DDS_SECURITY_LEVEL={security_level}",
        "-e",
        f"NET_PROFILE={net_profile}",
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        "PYTHONUNBUFFERED=1",
    ]

    if config_path is not None:
        arguments.extend(
            [
                "-e",
                f"CYCLONEDDS_URI={security_uri(config_path)}",
            ]
        )

    return arguments


def run_pair_control(
    *,
    control_id,
    description,
    campaign_dir,
    publisher_level,
    publisher_config,
    evidence_terms,
):
    suffix = uuid4().hex[:8]
    network_name = f"occ-dds-sec-{suffix}"
    publisher_name = f"occ-dds-sec-pub-{suffix}"
    subscriber_name = f"occ-dds-sec-sub-{suffix}"

    control_dir = campaign_dir / control_id
    control_dir.mkdir(parents=True, exist_ok=False)

    publisher_log_path = control_dir / "publisher.log"
    subscriber_log_path = control_dir / "subscriber.log"

    run_id = f"dds_{control_id}_{suffix}"
    containers = [publisher_name, subscriber_name]

    cleanup(containers, network_name)
    docker("network", "create", network_name)

    publisher_status = None
    subscriber_status = None
    publisher_log = ""
    subscriber_log = ""

    try:
        subscriber_command = [
            "run",
            "-d",
            "--name",
            subscriber_name,
            "--network",
            network_name,
            *docker_environment(
                "C2",
                control_id,
                run_id,
                CONTAINER_CONFIG_DIR / "c2_subscriber.xml",
            ),
            "-v",
            f"{PROJECT_DIR}:{CONTAINER_ROOT}",
            IMAGE,
            "python",
            SUBSCRIBER_PROGRAM,
            "--domain",
            "0",
            "--duration",
            "8",
        ]

        docker(*subscriber_command)
        time.sleep(1)

        publisher_command = [
            "run",
            "-d",
            "--name",
            publisher_name,
            "--network",
            network_name,
            *docker_environment(
                publisher_level,
                control_id,
                run_id,
                publisher_config,
            ),
            "-v",
            f"{PROJECT_DIR}:{CONTAINER_ROOT}",
            IMAGE,
            "python",
            PUBLISHER_PROGRAM,
            "--domain",
            "0",
            "--duration",
            "3",
            "--rate",
            "10",
            "--match-timeout",
            "4",
        ]

        docker(*publisher_command)

        publisher_status = wait_container(
            publisher_name
        )
        subscriber_status = wait_container(
            subscriber_name
        )

        publisher_log = container_logs(
            publisher_name
        )
        subscriber_log = container_logs(
            subscriber_name
        )

    finally:
        if not publisher_log:
            publisher_log = container_logs(
                publisher_name
            )

        if not subscriber_log:
            subscriber_log = container_logs(
                subscriber_name
            )

        publisher_log_path.write_text(
            publisher_log,
            encoding="utf-8",
        )
        subscriber_log_path.write_text(
            subscriber_log,
            encoding="utf-8",
        )

        cleanup(containers, network_name)

    combined_log = publisher_log + subscriber_log

    evidence = next(
        (
            term
            for term in evidence_terms
            if term.lower() in combined_log.lower()
        ),
        "No authenticated match or telemetry exchange",
    )

    passed = (
        publisher_status not in (None, 0)
        and subscriber_status not in (None, 0)
        and "PUBLISH |" not in publisher_log
        and "RECEIVE " not in subscriber_log
    )

    return {
        "control_id": control_id,
        "description": description,
        "verdict": "PASS" if passed else "FAIL",
        "publisher_exit_status": publisher_status,
        "subscriber_exit_status": subscriber_status,
        "evidence": evidence,
        "publisher_log": str(
            publisher_log_path.relative_to(PROJECT_DIR)
        ),
        "subscriber_log": str(
            subscriber_log_path.relative_to(PROJECT_DIR)
        ),
    }


def run_denied_permissions(campaign_dir):
    control_id = "denied_permissions"
    suffix = uuid4().hex[:8]
    container_name = f"occ-dds-sec-deny-{suffix}"

    control_dir = campaign_dir / control_id
    control_dir.mkdir(parents=True, exist_ok=False)

    program_path = control_dir / "unauthorized_writer.py"
    log_path = control_dir / "writer.log"

    program_path.write_text(
        """\
import sys

sys.path.insert(
    0,
    "/workspace/testbed/protocols/dds",
)

from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.topic import Topic

from dds_types import VehicleState


participant = DomainParticipant(0)

topic = Topic(
    participant,
    "UnauthorizedVehicleState",
    VehicleState,
)

DataWriter(participant, topic)

print("UNAUTHORIZED_WRITER_CREATED")
""",
        encoding="utf-8",
    )

    docker("rm", "-f", container_name, check=False)

    try:
        result = docker(
            "run",
            "--name",
            container_name,
            *docker_environment(
                "C2",
                control_id,
                f"dds_{control_id}_{suffix}",
                CONTAINER_CONFIG_DIR / "c2_publisher.xml",
            ),
            "-v",
            f"{PROJECT_DIR}:{CONTAINER_ROOT}",
            IMAGE,
            "python",
            container_path(program_path),
            check=False,
        )

        status = result.returncode
        log = (
            result.stdout
            + result.stderr
            + container_logs(container_name)
        )

    finally:
        docker(
            "rm",
            "-f",
            container_name,
            check=False,
        )

    log_path.write_text(log, encoding="utf-8")

    expected_error = (
        "NOT_ALLOWED_BY_SECURITY" in log
        or "permission denied" in log.lower()
        or "insufficient credentials" in log.lower()
    )

    passed = (
        status != 0
        and "UNAUTHORIZED_WRITER_CREATED" not in log
        and expected_error
    )

    return {
        "control_id": control_id,
        "description": (
            "C2 default-DENY blocks an unauthorized topic"
        ),
        "verdict": "PASS" if passed else "FAIL",
        "publisher_exit_status": status,
        "subscriber_exit_status": "",
        "evidence": (
            "DDS_RETCODE_NOT_ALLOWED_BY_SECURITY"
            if expected_error
            else "Expected permission denial not found"
        ),
        "publisher_log": str(
            log_path.relative_to(PROJECT_DIR)
        ),
        "subscriber_log": "",
    }


def generate_invalid_key_config(campaign_dir):
    config_path = (
        campaign_dir / "invalid_key_publisher.xml"
    )

    replace_config(
        CONTAINER_CONFIG_DIR / "c2_publisher.xml",
        config_path,
        {
            (
                "/workspace/testbed/config/dds/security/"
                "private/publisher_key.pem"
            ): (
                "/workspace/testbed/config/dds/security/"
                "private/subscriber_key.pem"
            ),
        },
    )

    return config_path


def generate_rogue_identity(campaign_dir):
    asset_dir = campaign_dir / "rogue_identity"
    asset_dir.mkdir(parents=True, exist_ok=False)

    ca_key = asset_dir / "rogue_identity_ca_key.pem"
    ca_cert = asset_dir / "rogue_identity_ca_cert.pem"
    publisher_key = asset_dir / "rogue_publisher_key.pem"
    publisher_csr = asset_dir / "rogue_publisher.csr"
    publisher_cert = asset_dir / "rogue_publisher_cert.pem"
    config_path = asset_dir / "rogue_c2_publisher.xml"

    commands = [
        [
            "openssl",
            "genrsa",
            "-out",
            str(ca_key),
            "2048",
        ],
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-key",
            str(ca_key),
            "-sha256",
            "-days",
            "3650",
            "-subj",
            (
                "/C=DE/ST=Saxony-Anhalt/L=Magdeburg/"
                "O=OvGU-IEPS/OU=OCC-Testbed/"
                "CN=Rogue-DDS-Identity-CA"
            ),
            "-out",
            str(ca_cert),
        ],
        [
            "openssl",
            "genrsa",
            "-out",
            str(publisher_key),
            "2048",
        ],
        [
            "openssl",
            "req",
            "-new",
            "-key",
            str(publisher_key),
            "-subj",
            (
                "/C=DE/ST=Saxony-Anhalt/L=Magdeburg/"
                "O=OvGU-IEPS/OU=OCC-Testbed/"
                "CN=DDS-Publisher"
            ),
            "-out",
            str(publisher_csr),
        ],
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(publisher_csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-days",
            "3650",
            "-sha256",
            "-out",
            str(publisher_cert),
        ],
    ]

    for command in commands:
        run(command)

    replace_config(
        CONTAINER_CONFIG_DIR / "c2_publisher.xml",
        config_path,
        {
            (
                "/workspace/testbed/config/dds/security/"
                "identity_ca_cert.pem"
            ): container_path(ca_cert),
            (
                "/workspace/testbed/config/dds/security/"
                "publisher_cert.pem"
            ): container_path(publisher_cert),
            (
                "/workspace/testbed/config/dds/security/"
                "private/publisher_key.pem"
            ): container_path(publisher_key),
        },
    )

    return config_path


def preflight():
    if shutil.which("docker") is None:
        raise RuntimeError("Docker was not found")

    if shutil.which("openssl") is None:
        raise RuntimeError("OpenSSL was not found")

    required_paths = [
        CONTAINER_CONFIG_DIR / "c2_publisher.xml",
        CONTAINER_CONFIG_DIR / "c2_subscriber.xml",
        SECURITY_DIR / "publisher_cert.pem",
        SECURITY_DIR / "subscriber_cert.pem",
        SECURITY_DIR / "identity_ca_cert.pem",
        SECURITY_DIR / "private" / "publisher_key.pem",
        SECURITY_DIR / "private" / "subscriber_key.pem",
    ]

    missing = [
        path
        for path in required_paths
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing DDS security files: "
            + ", ".join(str(path) for path in missing)
        )

    docker("image", "inspect", IMAGE)


def main():
    preflight()

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    campaign_id = (
        f"dds_security_controls_{timestamp}_"
        f"{uuid4().hex[:8]}"
    )

    campaign_dir = RESULTS_ROOT / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=False)

    print("DDS security-control campaign")
    print("Campaign:", campaign_id)
    print("Image:", IMAGE)

    invalid_config = generate_invalid_key_config(
        campaign_dir
    )
    rogue_config = generate_rogue_identity(
        campaign_dir
    )

    results = []

    controls = [
        (
            "downgrade_rejection",
            lambda: run_pair_control(
                control_id="downgrade_rejection",
                description=(
                    "C2 subscriber rejects unsecured C0 publisher"
                ),
                campaign_dir=campaign_dir,
                publisher_level="C0",
                publisher_config=None,
                evidence_terms=[
                    "No authenticated DDS subscriber matched",
                    "No DDS samples received",
                ],
            ),
        ),
        (
            "invalid_credential",
            lambda: run_pair_control(
                control_id="invalid_credential",
                description=(
                    "C2 rejects a certificate/private-key mismatch"
                ),
                campaign_dir=campaign_dir,
                publisher_level="C2",
                publisher_config=invalid_config,
                evidence_terms=[
                    "handshake failed",
                    "rsa_verify",
                    "certificate",
                ],
            ),
        ),
        (
            "denied_permissions",
            lambda: run_denied_permissions(
                campaign_dir
            ),
        ),
        (
            "untrusted_ca",
            lambda: run_pair_control(
                control_id="untrusted_ca",
                description=(
                    "C2 rejects identity signed by an untrusted CA"
                ),
                campaign_dir=campaign_dir,
                publisher_level="C2",
                publisher_config=rogue_config,
                evidence_terms=[
                    "unable to get local issuer certificate",
                    "Certificate not valid",
                    "No authenticated DDS subscriber matched",
                ],
            ),
        ),
    ]

    for control_name, execute in controls:
        print()
        print("=" * 72)
        print("Running:", control_name)
        print("=" * 72)

        result = execute()
        results.append(result)

        print(
            f"{result['verdict']}: "
            f"{result['description']}"
        )
        print("Evidence:", result["evidence"])

    summary_path = campaign_dir / "summary.csv"

    with summary_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as summary_file:
        writer = csv.DictWriter(
            summary_file,
            fieldnames=results[0].keys(),
        )
        writer.writeheader()
        writer.writerows(results)

    passed = sum(
        result["verdict"] == "PASS"
        for result in results
    )

    print()
    print("=" * 72)
    print("DDS SECURITY-CONTROL SUMMARY")
    print("=" * 72)

    for result in results:
        print(
            f"{result['verdict']:4} | "
            f"{result['control_id']}"
        )

    print()
    print(f"Passed: {passed}/{len(results)}")
    print("Summary:", summary_path)
    print("Evidence directory:", campaign_dir)

    if passed != len(results):
        raise RuntimeError(
            "One or more DDS security controls failed"
        )

    print("PASS: all DDS security controls validated")


if __name__ == "__main__":
    main()

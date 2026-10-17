from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
VALID = ROOT / "examples" / "valid"

runs = {}

for p in sorted(VALID.glob("run_metadata_*.json")):
    r = json.loads(p.read_text())
    runs[r["run_id"]] = r

    legit = [
        v for v in r["vehicle_instances"]
        if v["vehicle_role"] == "legitimate"
    ]
    attackers = [
        v for v in r["vehicle_instances"]
        if v["vehicle_role"] == "attacker"
    ]

    assert r["active_vehicle_count"] == len(legit), (
        p.name,
        "active_vehicle_count mismatch"
    )

    assert r["active_attacker_count"] == len(attackers), (
        p.name,
        "active_attacker_count mismatch"
    )

    expected_hw = {v["hardware_unit_id"] for v in r["vehicle_instances"]}
    actual_hw = set(r["participating_hardware_unit_ids"])

    assert expected_hw == actual_hw, (
        p.name,
        "participating_hardware_unit_ids mismatch"
    )

    expected_serial = {
        v["serialNumber"]
        for v in legit
        if v["serialNumber"] is not None
    }

    assert expected_serial == set(r["participating_serial_numbers"]), (
        p.name,
        "participating_serial_numbers mismatch"
    )

    paths = {x["network_path_id"] for x in r["network_paths"]}

    for v in r["vehicle_instances"]:
        assert v["network_path_id"] in paths, (
            p.name,
            f"unknown network_path_id for {v['hardware_unit_id']}"
        )

        assert v["protocol"] == r["protocol"], (
            p.name,
            "vehicle/run protocol mismatch"
        )

        assert v["security_profile"] == r["security_profile"], (
            p.name,
            "vehicle/run security profile mismatch"
        )

    services = {s["service_id"] for s in r["occ_services"]}

    if r["middleware_service_id"] is not None:
        assert r["middleware_service_id"] in services, (
            p.name,
            "middleware_service_id missing from occ_services"
        )

    if r["occ_deployment_mode"] == "docker":
        deployment_ids = {
            x["container_instance_id"]
            for x in r["container_instances"]
        }

        for s in r["occ_services"]:
            for d in s["deployment_instance_ids"]:
                assert d in deployment_ids, (
                    p.name,
                    f"unknown Docker deployment instance {d}"
                )

    elif r["occ_deployment_mode"] == "k3s":
        deployment_ids = {
            x["workload_id"]
            for x in r["k3s_workloads"]
        }

        for s in r["occ_services"]:
            for d in s["deployment_instance_ids"]:
                assert d in deployment_ids, (
                    p.name,
                    f"unknown K3s workload {d}"
                )

    elif r["occ_deployment_mode"] == "native":
        for s in r["occ_services"]:
            for d in s["deployment_instance_ids"]:
                assert d.startswith("native:"), (
                    p.name,
                    f"native deployment ID must start native: {d}"
                )

    if r["network_stage"] == "wireguard":
        assert r["wireguard"]["enabled"] is True, (
            p.name,
            "wireguard stage without enabled tunnel"
        )
    else:
        assert r["wireguard"]["enabled"] is False, (
            p.name,
            "WireGuard enabled outside wireguard stage"
        )

    vehicle_by_hw = {
        v["hardware_unit_id"]: v
        for v in r["vehicle_instances"]
    }

    for a in r["attack_scenarios"]:
        attacker = vehicle_by_hw[a["attacker_hardware_unit_id"]]

        assert attacker["vehicle_role"] == "attacker", (
            p.name,
            "attack scenario attacker is not attacker role"
        )

        for target in a["target_hardware_unit_ids"]:
            assert target in vehicle_by_hw, (
                p.name,
                f"unknown attack target {target}"
            )

            assert vehicle_by_hw[target]["vehicle_role"] == "legitimate", (
                p.name,
                "attack target must be legitimate"
            )

        w = a["attack_window_definition"]

        assert w["basis"] == "victim_seq_range"

        assert 0 <= w["victim_seq_start"] <= w["victim_seq_end"] <= 599

print("Run metadata semantic checks: PASS")

raw = json.loads((VALID / "raw_row_valid.json").read_text())
r = runs[raw["run_id"]]

assert raw["hardware_unit_id"] in {
    v["hardware_unit_id"]
    for v in r["vehicle_instances"]
}

match = [
    v for v in r["vehicle_instances"]
    if v["hardware_unit_id"] == raw["hardware_unit_id"]
][0]

assert match["serialNumber"] == raw["serialNumber"]
assert match["vehicle_role"] == raw["vehicle_role"]
assert raw["active_vehicle_count"] == r["active_vehicle_count"]
assert raw["active_attacker_count"] == r["active_attacker_count"]

print("Raw-row/run join check: PASS")

occ = json.loads(
    (VALID / "occ_message_event_valid.json").read_text()
)
r = runs[occ["run_id"]]

assert occ["service_id"] in {
    s["service_id"]
    for s in r["occ_services"]
}

assert occ["event_source_layer"] == "fair_echo_application"

print("OCC event provenance check: PASS")

attack_path = VALID / "attack_event_valid.json"

if attack_path.exists():
    event = json.loads(attack_path.read_text())
    r = runs[event["run_id"]]

    attack_ids = {
        a["attack_id"]
        for a in r["attack_scenarios"]
    }

    assert event["attack_id"] in attack_ids

    print("Attack-event/run join check: PASS")

for p in sorted(VALID.glob("occ_system_*.json")):
    s = json.loads(p.read_text())

    if s["sampling_scope"] == "service-aggregate":
        assert s["metric_aggregation_methods"] is not None
        assert len(s["aggregation_member_ids"]) > 0
        assert s["aggregation_member_scope"] is not None
    else:
        assert s["metric_aggregation_methods"] is None
        assert s["aggregation_member_ids"] == []
        assert s["aggregation_member_scope"] is None

print("OCC system-sampling scope checks: PASS")

print()
print("PHASE 0C SEMANTIC AUDIT: PASS")

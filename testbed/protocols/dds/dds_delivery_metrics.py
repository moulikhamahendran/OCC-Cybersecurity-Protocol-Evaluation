import hashlib
import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DeliveryMetrics:
    eligible_sent_count: int
    unique_received_count: int
    lost_count: int
    loss_percent: float
    duplicate_count: int
    identical_duplicate_count: int
    conflicting_duplicate_count: int
    unexpected_count: int
    startup_count: int
    lost_ids: tuple[int, ...]
    unexpected_ids: tuple[int, ...]


def payload_fingerprint(payload) -> str:
    if isinstance(payload, bytes):
        encoded = payload
    elif isinstance(payload, str):
        encoded = payload.encode("utf-8")
    else:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def calculate_delivery_metrics(
    eligible_sent_ids: Iterable[int],
    received_samples: Iterable[tuple[int, object]],
    startup_ids: Iterable[int] = (),
) -> DeliveryMetrics:
    eligible = {int(value) for value in eligible_sent_ids}
    startup = {int(value) for value in startup_ids}

    received_hashes: dict[int, str] = {}
    unexpected_ids: set[int] = set()

    identical_duplicates = 0
    conflicting_duplicates = 0
    unexpected_count = 0
    startup_count = 0

    for raw_header_id, payload in received_samples:
        header_id = int(raw_header_id)

        if header_id not in eligible:
            if header_id in startup:
                startup_count += 1
            else:
                unexpected_count += 1
                unexpected_ids.add(header_id)
            continue

        fingerprint = payload_fingerprint(payload)

        if header_id in received_hashes:
            if received_hashes[header_id] == fingerprint:
                identical_duplicates += 1
            else:
                conflicting_duplicates += 1
            continue

        received_hashes[header_id] = fingerprint

    received_ids = set(received_hashes)
    lost_ids = eligible - received_ids
    eligible_count = len(eligible)

    loss_percent = (
        len(lost_ids) / eligible_count * 100
        if eligible_count
        else 0.0
    )

    return DeliveryMetrics(
        eligible_sent_count=eligible_count,
        unique_received_count=len(received_ids),
        lost_count=len(lost_ids),
        loss_percent=loss_percent,
        duplicate_count=(
            identical_duplicates + conflicting_duplicates
        ),
        identical_duplicate_count=identical_duplicates,
        conflicting_duplicate_count=conflicting_duplicates,
        unexpected_count=unexpected_count,
        startup_count=startup_count,
        lost_ids=tuple(sorted(lost_ids)),
        unexpected_ids=tuple(sorted(unexpected_ids)),
    )

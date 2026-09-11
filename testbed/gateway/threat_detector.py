import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone


REPLAY_WINDOW_SECONDS = 10.0
STALE_THRESHOLD_SECONDS = 5.0
DOS_THRESHOLD_PER_SECOND = 50

TRUSTED_SERIAL_NUMBERS = {
    value.strip()
    for value in os.getenv(
        "TRUSTED_SERIAL_NUMBERS",
        "VM-001",
    ).split(",")
    if value.strip()
}


class ThreatDetector:
    def __init__(self):
        self.recent_headers = defaultdict(dict)
        self.message_times = defaultdict(deque)

    def detect(self, payload: dict) -> list[dict]:
        """Return all detected threats for one validated message."""

        threats = []

        serial_number = payload["serialNumber"]
        header_id = payload["headerId"]
        current_monotonic = time.monotonic()

        spoofing_reason = self._check_spoofing(
            serial_number
        )

        if spoofing_reason:
            threats.append(
                {
                    "type": "spoofing",
                    "action": "BLOCK",
                    "reason": spoofing_reason,
                }
            )

        replay_reason = self._check_replay(
            serial_number,
            header_id,
            current_monotonic,
        )

        if replay_reason:
            threats.append(
                {
                    "type": "replay",
                    "action": "BLOCK",
                    "reason": replay_reason,
                }
            )

        stale_reason = self._check_stale(
            payload["timestamp"]
        )

        if stale_reason:
            threats.append(
                {
                    "type": "stale_message",
                    "action": "BLOCK",
                    "reason": stale_reason,
                }
            )

        dos_reason = self._check_dos(
            serial_number,
            current_monotonic,
        )

        if dos_reason:
            threats.append(
                {
                    "type": "dos_rate",
                    "action": "BLOCK",
                    "reason": dos_reason,
                }
            )

        return threats

    def _check_spoofing(
        self,
        serial_number: str,
    ) -> str | None:

        if (
            TRUSTED_SERIAL_NUMBERS
            and serial_number not in TRUSTED_SERIAL_NUMBERS
        ):
            return (
                f"Untrusted vehicle identity "
                f"{serial_number}; trusted vehicles are "
                f"{sorted(TRUSTED_SERIAL_NUMBERS)}"
            )

        return None

    def _check_replay(
        self,
        serial_number: str,
        header_id: int,
        current_time: float,
    ) -> str | None:

        vehicle_headers = self.recent_headers[
            serial_number
        ]

        expired_headers = [
            stored_header
            for stored_header, seen_time
            in vehicle_headers.items()
            if current_time - seen_time
            > REPLAY_WINDOW_SECONDS
        ]

        for expired_header in expired_headers:
            del vehicle_headers[expired_header]

        if header_id in vehicle_headers:
            return (
                f"Duplicate headerId {header_id} "
                f"received within "
                f"{REPLAY_WINDOW_SECONDS:.0f} seconds"
            )

        vehicle_headers[header_id] = current_time

        return None

    def _check_stale(
        self,
        timestamp_text: str,
    ) -> str | None:

        try:
            message_time = datetime.fromisoformat(
                timestamp_text.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            return "Timestamp could not be parsed"

        if message_time.tzinfo is None:
            message_time = message_time.replace(
                tzinfo=timezone.utc
            )

        age_seconds = (
            datetime.now(timezone.utc)
            - message_time
        ).total_seconds()

        if age_seconds > STALE_THRESHOLD_SECONDS:
            return (
                f"Message age {age_seconds:.3f} seconds "
                f"exceeds "
                f"{STALE_THRESHOLD_SECONDS:.0f} seconds"
            )

        return None

    def _check_dos(
        self,
        serial_number: str,
        current_time: float,
    ) -> str | None:

        timestamps = self.message_times[
            serial_number
        ]

        timestamps.append(
            current_time
        )

        while (
            timestamps
            and current_time - timestamps[0] > 1.0
        ):
            timestamps.popleft()

        current_rate = len(timestamps)

        if current_rate > DOS_THRESHOLD_PER_SECOND:
            return (
                f"Message rate {current_rate} "
                f"messages/second exceeds limit of "
                f"{DOS_THRESHOLD_PER_SECOND}"
            )

        return None

import sys
from pathlib import Path


TESTBED_DIR = Path(__file__).resolve().parents[1]
DDS_DIR = TESTBED_DIR / "protocols" / "dds"

sys.path.insert(0, str(DDS_DIR))

from dds_delivery_metrics import calculate_delivery_metrics


def samples(ids, prefix="payload"):
    return [
        (header_id, f"{prefix}-{header_id}")
        for header_id in ids
    ]


# Case 1: 100 sent, 100 unique received.
result = calculate_delivery_metrics(
    range(100),
    samples(range(100)),
)
assert result.unique_received_count == 100
assert result.lost_count == 0
assert result.loss_percent == 0.0


# Case 2: 100 sent, 95 unique received.
result = calculate_delivery_metrics(
    range(100),
    samples(range(95)),
)
assert result.unique_received_count == 95
assert result.lost_count == 5
assert result.lost_ids == (95, 96, 97, 98, 99)
assert result.loss_percent == 5.0


# Case 3: duplicates must not alter delivery or loss.
received = samples(range(100))
received.extend([
    (10, "payload-10"),
    (20, "payload-20"),
])

result = calculate_delivery_metrics(range(100), received)
assert result.unique_received_count == 100
assert result.duplicate_count == 2
assert result.identical_duplicate_count == 2
assert result.conflicting_duplicate_count == 0
assert result.lost_count == 0


# Case 4: startup messages are reported separately.
received = samples(range(10), prefix="startup")
received.extend(samples(range(10, 110)))

result = calculate_delivery_metrics(
    range(10, 110),
    received,
    startup_ids=range(10),
)
assert result.unique_received_count == 100
assert result.startup_count == 10
assert result.unexpected_count == 0
assert result.lost_count == 0


# Case 5: unexpected ID cannot improve loss.
received = samples(range(95))
received.append((999, "unexpected-message"))

result = calculate_delivery_metrics(range(100), received)
assert result.unique_received_count == 95
assert result.unexpected_count == 1
assert result.unexpected_ids == (999,)
assert result.lost_count == 5
assert result.loss_percent == 5.0


# Case 6a: same ID and same payload is identical duplicate.
result = calculate_delivery_metrics(
    [7],
    [
        (7, "same-payload"),
        (7, "same-payload"),
    ],
)
assert result.identical_duplicate_count == 1
assert result.conflicting_duplicate_count == 0
assert result.lost_count == 0


# Case 6b: same ID and different payload is conflicting duplicate.
result = calculate_delivery_metrics(
    [7],
    [
        (7, "original-payload"),
        (7, "tampered-payload"),
    ],
)
assert result.identical_duplicate_count == 0
assert result.conflicting_duplicate_count == 1
assert result.duplicate_count == 1
assert result.lost_count == 0


print("PASS: clean delivery")
print("PASS: genuine loss")
print("PASS: identical duplicates")
print("PASS: startup exclusion")
print("PASS: unexpected-message isolation")
print("PASS: conflicting duplicate detection")
print("All six DDS delivery-metric cases passed")

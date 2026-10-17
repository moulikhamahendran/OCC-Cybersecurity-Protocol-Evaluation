"""Live dashboard view of sanitized OPC UA receive events (not benchmark evidence)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

PROFILE_NAMES = frozenset({'C0', 'C1', 'C2'})
VEHICLE_RE = re.compile(r'^[A-Za-z0-9_-]{1,63}$')
DEFAULT_STATE = '/var/lib/occ-dashboard/opcua-live/state.json'
OFFLINE_AFTER_SECONDS = 5.0


def opcua_live_snapshot(*, path=None, now=None):
    target = Path(path or os.getenv('OCC_OPCUA_LIVE_STATE', DEFAULT_STATE))
    current = now or datetime.now(timezone.utc)
    vehicles = []
    error = None
    try:
        if target.is_symlink() or not target.is_file():
            error = 'observer_state_not_available'
        elif target.stat().st_size > 262144:
            error = 'observer_state_too_large'
        else:
            data = json.loads(target.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('schema_version') != 1:
                error = 'observer_state_invalid'
            else:
                records = data.get('vehicles', [])
                if not isinstance(records, list):
                    error = 'observer_vehicles_invalid'
                else:
                    for record in records[:30]:
                        if not isinstance(record, dict):
                            continue
                        vehicle = record.get('vehicle_id')
                        profile = record.get('security_profile')
                        seq = record.get('seq')
                        timestamp = record.get('last_rx_utc')
                        if not (isinstance(vehicle, str) and VEHICLE_RE.fullmatch(vehicle)):
                            continue
                        if profile not in PROFILE_NAMES:
                            continue
                        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
                            continue
                        if not isinstance(timestamp, str):
                            continue
                        try:
                            when = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            if when.tzinfo is None:
                                continue
                            age = (current - when.astimezone(timezone.utc)).total_seconds()
                        except ValueError:
                            continue
                        # Future timestamps must not masquerade as fresh presence.
                        online = 0 <= age <= OFFLINE_AFTER_SECONDS
                        vehicles.append({
                            'vehicle_id': vehicle,
                            'protocol': 'opcua',
                            'security_profile': profile,
                            'seq': seq,
                            'last_seen_utc': timestamp,
                            'age_seconds': round(max(age, 0.0), 3),
                            'online': online,
                            'telemetry': {
                                'speed': None,
                                'pos_x': None,
                                'pos_y': None,
                                'heading': None,
                                'battery_pct': None,
                                'state': None,
                            },
                            'telemetry_availability': 'identity_seq_only',
                            'source': 'new_opcua_occ_rx',
                        })
    except (OSError, UnicodeError, ValueError, TypeError):
        error = 'observer_state_unreadable'
    vehicles.sort(key=lambda v: v['vehicle_id'])
    return {
        'source': 'fresh-opcua-occ-rx',
        'scientific_evidence': False,
        'available': error is None,
        'reason': error,
        'protocol': 'opcua',
        'online_rule': {'offline_after_seconds': OFFLINE_AFTER_SECONDS},
        'vehicle_count': len(vehicles),
        'online_count': sum(v['online'] for v in vehicles),
        'vehicles': vehicles,
    }


def unified_vehicle_snapshot(mqtt_store):
    mqtt = mqtt_store.snapshot()
    opcua = opcua_live_snapshot()
    if not opcua['vehicles']:
        return mqtt
    merged = {v['vehicle_id']: v for v in mqtt['vehicles']}
    for v in opcua['vehicles']:
        prior = merged.get(v['vehicle_id'])
        if prior is None:
            merged[v['vehicle_id']] = v
        elif v['online'] and not prior['online']:
            merged[v['vehicle_id']] = v
        elif not v['online'] and prior['online']:
            continue
        else:
            # Prefer the most recent actual reception, never protocol order.
            try:
                a = datetime.fromisoformat(v['last_seen_utc'].replace('Z', '+00:00'))
                b = datetime.fromisoformat(prior['last_seen_utc'].replace('Z', '+00:00'))
                if a >= b:
                    merged[v['vehicle_id']] = v
            except (ValueError, KeyError, TypeError):
                pass
    vehicles = [merged[k] for k in sorted(merged)]
    return {
        **mqtt,
        'protocol': 'multi',
        'vehicle_count': len(vehicles),
        'online_count': sum(v['online'] for v in vehicles),
        'vehicles': vehicles,
        'opcua_observer_available': opcua['available'],
    }

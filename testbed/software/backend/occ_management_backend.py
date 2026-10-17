"""OCC authenticated lab management plane (independent from data protocol).

Security: per-vehicle 256-bit HMAC key, non-retained commands, bounded lifetime,
operator bearer secret, socket poll/response nonce binding, no unauthenticated writes.
An isolated lab prototype: UDP payload confidentiality is NOT provided.
"""
from __future__ import annotations
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

MGMT_CONFIG = Path(os.environ.get('OCC_MGMT_CONFIG', '/etc/occ-dashboard/management.json'))
MGMT_STATE = Path(os.environ.get('OCC_MGMT_STATE_DIR', '/var/lib/occ-dashboard/management'))
PORT = int(os.environ.get('OCC_MGMT_UDP_PORT', '18081'))
VEHICLE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
NONCE = re.compile(r'^[0-9a-f]{16}$')
REQ_ID = re.compile(r'^[0-9a-f]{32}$')
PROTOCOLS = {'MQTT', 'OPCUA', 'DDS'}   # DDS C0 only; C1/C2 still disabled
PROFILES = {'C0', 'C1', 'C2'}
TTL = 120.0
router = APIRouter(prefix='/api/v1/management', tags=['management'])


def config() -> dict:
    doc = json.loads(MGMT_CONFIG.read_text())
    if not isinstance(doc.get('operator_token'), str) or len(doc['operator_token']) != 64:
        raise RuntimeError('Missing valid 256-bit operator token')
    if not isinstance(doc.get('devices'), dict):
        raise RuntimeError('Missing vehicle keys')
    for v, key in doc['devices'].items():
        if not VEHICLE.fullmatch(v) or not re.fullmatch('[0-9a-f]{64}', key):
            raise RuntimeError('Invalid management vehicle/key')
    return doc


def mac(keyhex: str, msg: str) -> str:
    return hmac.new(bytes.fromhex(keyhex), msg.encode('ascii'), hashlib.sha256).hexdigest()


@contextmanager
def locked_state():
    MGMT_STATE.mkdir(parents=True, exist_ok=True)
    lock = MGMT_STATE / 'lock'
    with lock.open('a+b') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        path = MGMT_STATE / 'requests.json'
        records = json.loads(path.read_text()) if path.exists() else {}
        try:
            yield records
            fd, temp = tempfile.mkstemp(dir=MGMT_STATE, prefix='.requests-')
            try:
                with os.fdopen(fd, 'w') as handle:
                    json.dump(records, handle, separators=(',', ':'))
                    handle.write('\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp, 0o640)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def expire(record: dict) -> None:
    if record.get('phase') in ('queued', 'device_confirmed') and time.time() > record['expires_at']:
        record['phase'] = 'timeout'


class SwitchBody(BaseModel):
    protocol: str
    profile: str


def auth(value: str | None) -> None:
    try:
        expected = config()['operator_token']
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(status_code=503, detail='Management not configured')
    if not value or not hmac.compare_digest(value, expected):
        raise HTTPException(status_code=403, detail='Operator authentication failed')


@router.post('/vehicles/{vehicle_id}/switch')
def request_switch(vehicle_id: str, body: SwitchBody, x_occ_operator_token: str | None = Header(default=None)) -> dict:
    auth(x_occ_operator_token)
    if not VEHICLE.fullmatch(vehicle_id) or vehicle_id not in config()['devices']:
        raise HTTPException(status_code=404, detail='Vehicle is not provisioned')
    protocol, profile = body.protocol.upper(), body.profile.upper()
    if protocol not in PROTOCOLS or profile not in PROFILES or (protocol == 'DDS' and profile != 'C0'):
        raise HTTPException(status_code=400, detail='Unsupported protocol/security mode')
    now = time.time()
    with locked_state() as records:
        old = records.get(vehicle_id)
        if old:
            expire(old)
            if old.get('phase') in ('queued', 'device_confirmed'):
                raise HTTPException(status_code=409, detail='Another switch remains pending')
        record = {'request_id': secrets.token_hex(16), 'vehicle_id': vehicle_id,
                  'protocol': protocol, 'profile': profile, 'phase': 'queued',
                  'requested_at': now, 'expires_at': now + TTL}
        records[vehicle_id] = record
    return sanitize(record)


def sanitize(record: dict) -> dict:
    return {k: record.get(k) for k in ('request_id', 'vehicle_id', 'protocol', 'profile', 'phase', 'requested_at', 'expires_at')}


@router.get('/vehicles/{vehicle_id}/link')
def link_status(vehicle_id: str) -> dict:
    if not VEHICLE.fullmatch(vehicle_id):
        raise HTTPException(status_code=404, detail='Vehicle not found')
    with locked_state() as records:
        item = records.get('_links', {}).get(vehicle_id)
        if not isinstance(item, dict):
            return {'vehicle_id': vehicle_id, 'online': False, 'age_seconds': None}
        age = max(0., time.time() - item['time'])
        return {'vehicle_id': vehicle_id, 'online': age < 20., 'age_seconds': round(age, 1),
                'protocol': item['protocol'], 'profile': item['profile']}


@router.get('/vehicles/{vehicle_id}/status')
def switch_status(vehicle_id: str) -> dict:
    if not VEHICLE.fullmatch(vehicle_id):
        raise HTTPException(status_code=404, detail='Vehicle not found')
    with locked_state() as records:
        record = records.get(vehicle_id)
        if record is None:
            return {'vehicle_id': vehicle_id, 'phase': 'idle'}
        expire(record)
        if record['phase'] == 'device_confirmed':
            try:
                from .opcua_live import unified_vehicle_snapshot
                fleet = unified_vehicle_snapshot()
                matches = [v for v in fleet.get('vehicles', []) if v.get('vehicle_id') == vehicle_id]
                if any(v.get('online') and str(v.get('protocol', '')).upper().replace(' ', '') == record['protocol']
                       and v.get('security_profile') == record['profile'] for v in matches):
                    record['phase'] = 'verified'
            except (OSError, ValueError, KeyError, ImportError, TypeError):
                pass
        return sanitize(record)


def handle_poll(payload: bytes, addr: tuple, state: dict) -> bytes | None:
    try:
        if len(payload) > 255:
            return None
        data = payload.decode('ascii').strip().split('|')
        if len(data) != 7 or data[0] != 'POLL1':
            return None
        prefix, vid, nonce, applied, protocol, profile, signature = data
        keyhex = state['devices'].get(vid)
        if keyhex is None or not VEHICLE.fullmatch(vid) or not NONCE.fullmatch(nonce):
            return None
        if applied != '-' and not REQ_ID.fullmatch(applied):
            return None
        if protocol not in PROTOCOLS or profile not in PROFILES or (protocol == 'DDS' and profile != 'C0'):
            return None
        base = '|'.join(data[:-1])
        if not hmac.compare_digest(mac(keyhex, base), signature):
            return None
        # Limit replay of old polls while preserving reasonable memory bounds.
        cache = state.setdefault('_seen', {})
        now = time.monotonic()
        recent = cache.setdefault(vid, {})
        if nonce in recent:
            return None
        if len(recent) > 128:
            recent.clear()
        recent[nonce] = now
        with locked_state() as records:
            records.setdefault('_links', {})[vid] = {
                'time': time.time(), 'protocol': protocol, 'profile': profile}
            rec = records.get(vid)
            if rec is not None:
                expire(rec)
                if (rec['phase'] == 'queued' and applied == rec['request_id']
                        and protocol == rec['protocol'] and profile == rec['profile']):
                    rec['phase'] = 'device_confirmed'
                if rec['phase'] == 'queued':
                    request_id, target_protocol, target_profile = rec['request_id'], rec['protocol'], rec['profile']
                else:
                    request_id, target_protocol, target_profile = '-', '-', '-'
            else:
                request_id, target_protocol, target_profile = '-', '-', '-'
        kind = 'CMD1' if request_id != '-' else 'NOP1'
        body = f'{kind}|{vid}|{nonce}|{request_id}|{target_protocol}|{target_profile}'
        return (body + '|' + mac(keyhex, body)).encode('ascii')
    except (UnicodeError, ValueError, OSError, KeyError, TypeError):
        return None


def serve() -> None:
    cfg = config()
    MGMT_STATE.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('0.0.0.0', PORT))
        sock.settimeout(3)
        print(f'OCC management UDP control listening on {PORT}', flush=True)
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            result = handle_poll(data, addr, cfg)
            if result:
                sock.sendto(result, addr)


if __name__ == '__main__':
    serve()

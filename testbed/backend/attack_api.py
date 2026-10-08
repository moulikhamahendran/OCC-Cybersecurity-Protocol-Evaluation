"""VM-003 bounded testbed control; requires operator token, no automatic attacks."""
import hmac
import secrets
import os
import threading
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/mqtt/attacker", tags=["VM-003 attacker"])
_lock = threading.RLock()
_state = {"mode":"IDLE", "phase":"idle", "last_status":None, "updated":0, "deadline":0}
MODES = {"MALFORMED","REPLAY","SPOOF","FLOOD"}

class AttackCommand(BaseModel):
    mode: str

# OCC_OPERATOR_SESSION_V1 — volatile server-side sessions, never put secrets into localStorage.
_SESSION_COOKIE = "occ_operator_session"
_SESSION_SECONDS = 8 * 60 * 60
_sessions = {}  # id -> expiry; cleared by backend restart
_login_attempts = {} # client ip -> timestamps (limited memory/size)

class OperatorLogin(BaseModel):
    password: str = Field(min_length=1, max_length=512)

def _allowed_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Origin not allowed")
    # Production is reachable via Pi VPN. Recommend TLS reverse proxy for other networks.

def _configured_password():
    password = os.environ.get("OCC_ATTACK_OPERATOR_TOKEN", "")
    if len(password) < 32:
        raise HTTPException(503, "Operator login not configured")
    return password

def _active_session(request: Request):
    sid = request.cookies.get(_SESSION_COOKIE, "")
    if len(sid) != 64:
        return False
    now = time.time()
    with _lock:
        expiry = _sessions.get(sid, 0)
        if expiry <= now:
            _sessions.pop(sid, None)
            return False
    return True

def _auth(request: Request, authorization: str | None):
    _configured_password()
    _allowed_origin(request)
    if _active_session(request):
        return
    # Backwards compatibility for existing, authenticated Pi-local API scripts.
    if authorization and authorization.startswith("Bearer ") and hmac.compare_digest(authorization[7:], _configured_password()):
        return
    raise HTTPException(401, "Operator login required")

@router.get("/session")
def operator_session(request: Request):
    return {"authenticated": _active_session(request), "expires_after_seconds": _SESSION_SECONDS}

@router.post("/login")
def operator_login(body: OperatorLogin, request: Request, response: Response):
    _allowed_origin(request)
    expected = _configured_password()
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _lock:
        recent = [t for t in _login_attempts.get(ip, []) if now-t < 300]
        if len(recent) >= 5:
            raise HTTPException(429, "Too many attempts; retry after 5 minutes")
        if not hmac.compare_digest(body.password, expected):
            _login_attempts[ip] = recent + [now]
            raise HTTPException(401, "Invalid operator password")
        _login_attempts.pop(ip, None)
        # Bound retained session state and evict expired entries.
        for sid, expiry in list(_sessions.items()):
            if expiry <= now: _sessions.pop(sid, None)
        if len(_sessions) >= 128:
            raise HTTPException(503, "Session limit reached")
        sid = secrets.token_hex(32)
        _sessions[sid] = now + _SESSION_SECONDS
    response.set_cookie(
        key=_SESSION_COOKIE, value=sid, httponly=True,
        secure=(request.url.scheme == "https"), samesite="strict",
        max_age=_SESSION_SECONDS, path="/api/v1/mqtt/attacker",
    )
    return {"authenticated": True, "expires_after_seconds": _SESSION_SECONDS}

@router.post("/logout")
def operator_logout(request: Request, response: Response):
    _allowed_origin(request)
    sid = request.cookies.get(_SESSION_COOKIE, "")
    with _lock:
        _sessions.pop(sid, None)
    response.delete_cookie(_SESSION_COOKIE, path="/api/v1/mqtt/attacker", samesite="strict")
    return {"authenticated": False}

def observe_status(profile, topic, payload):
    if profile!="C2" or topic!="occ/runtime/C2/VM-003/status":
        return
    import json
    try:
        obj=json.loads(payload)
    except (ValueError,TypeError):
        return
    if obj.get("vehicle_id")!="VM-003":
        return
    with _lock:
        _state["last_status"]={k:obj.get(k) for k in ("vehicle_id","attack_mode","controller_result","execution_enabled")}
        _state["updated"]=time.time()
        result=obj.get("controller_result")
        if result in ("stopped_idle","idle_after_attack") and obj.get("attack_mode")=="IDLE":
            _state.update(mode="IDLE",phase="idle",deadline=0)
        elif result=="armed_ready" and obj.get("attack_mode") in MODES:
            _state.update(mode=obj["attack_mode"],phase="active")

def _auto_stop():
    from .main import mqtt_control_manager
    import json
    with _lock:
        if _state["phase"] not in ("requested", "active", "unconfirmed"):
            return
        c=mqtt_control_manager._clients.get("C2")
        if c and mqtt_control_manager._profiles["C2"]["connected"]:
            c.publish("occ/runtime/C2/VM-003/control", json.dumps({"command":"stop_attack"}), qos=1, retain=False)
        _state.update(phase="stopping", updated=time.time())

def _snapshot():
    with _lock:
        result=dict(_state)
    if result["phase"] in ("requested","active","stopping") and time.time()-result["updated"]>30:
        result["phase"]="unconfirmed"
    return result

@router.get("/state")
def state(request: Request, authorization: str | None=Header(default=None)):
    _auth(request,authorization)
    return _snapshot()

@router.post("/command")
def command(body: AttackCommand, request: Request, authorization: str | None=Header(default=None)):
    _auth(request,authorization)
    mode=body.mode.upper()
    if mode not in MODES | {"STOP"}:
        raise HTTPException(400,"Unknown attack mode")
    from .main import mqtt_control_manager
    from .live_state import live_vehicle_store
    from paho.mqtt import client as mqtt
    vehicle=live_vehicle_store.get("VM-003")
    if not vehicle or not vehicle.get("online") or vehicle.get("security_profile")!="C2":
        raise HTTPException(409,"VM-003 must be online in C2")
    with _lock:
        c=mqtt_control_manager._clients.get("C2")
        ready=mqtt_control_manager._profiles["C2"]["connected"]
        if not c or not ready:
            raise HTTPException(503,"C2 control unavailable")
        if mode!="STOP" and _state["phase"] not in ("idle","unconfirmed"):
            raise HTTPException(409,"An attack request is already pending or active")
        import json
        data={"command":"stop_attack"} if mode=="STOP" else {"command":"arm_attack","mode":mode}
        info=c.publish("occ/runtime/C2/VM-003/control",json.dumps(data),qos=1,retain=False)
        if info.rc!=mqtt.MQTT_ERR_SUCCESS:
            raise HTTPException(503,"MQTT publish failed")
        _state.update(mode=mode if mode!="STOP" else _state["mode"],phase="stopping" if mode=="STOP" else "requested",updated=time.time())
        if mode != "STOP":
            timer=threading.Timer(12.0, _auto_stop)
            timer.daemon=True
            timer.start()
    return {"command_sent":True,"confirmed":False,"mode":mode,"note":"Wait for VM-003 status acknowledgement"}

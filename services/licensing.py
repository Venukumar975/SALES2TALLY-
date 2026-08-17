import os
import sys
import json
import time
import base64
import hmac
import hashlib
import subprocess
import threading
import winreg
from datetime import datetime

from config import LOCAL_APP_DATA

# Shared Secret for validating signed license keys
SECRET_KEY = b"SALES_REG_2026_MASTER_SECRET_KEY_99a8b7c6d5e4f3"

LICENSE_DIR = os.path.join(LOCAL_APP_DATA, "SALES2TALLY")
LICENSE_FILE = os.path.join(LICENSE_DIR, "license.lic")

# Global in-memory license status flag
_LICENSE_STATE = {
    "is_valid": False,
    "status": "uninitialized",
    "hwid": "",
    "expiry_text": "",
    "type": "NONE",
    "remaining_seconds": 0
}

_STATE_LOCK = threading.Lock()
_HEARTBEAT_STARTED = False
_CACHED_HWID = None

def get_machine_hwid() -> str:
    """
    Generate a stable, unique 16-character hardware signature for this machine.
    Combines Windows MachineGuid, Motherboard UUID, and CPU Processor ID.
    Cached in-memory to prevent repeated subprocess calls.
    """
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    guid_str = ""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            guid_str, _ = winreg.QueryValueEx(key, "MachineGuid")
    except Exception:
        pass

    no_window = 0x08000000 if sys.platform == "win32" else 0

    uuid_str = ""
    try:
        # Motherboard UUID via PowerShell CIM (completely silent, no cmd window)
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=no_window)
        if proc.returncode == 0:
            uuid_str = proc.stdout.strip()
    except Exception:
        pass

    cpu_str = ""
    try:
        # CPU ID (completely silent, no cmd window)
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_Processor).ProcessorId"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=no_window)
        if proc.returncode == 0:
            cpu_str = proc.stdout.strip()
    except Exception:
        pass

    # Fallback to username/computer name if hardware IDs fail
    combined = f"{guid_str}|{uuid_str}|{cpu_str}".strip()
    if not combined or combined == "||":
        combined = f"{os.environ.get('COMPUTERNAME', '')}-{os.environ.get('USERNAME', '')}"

    h = hashlib.sha256(combined.encode("utf-8")).hexdigest().upper()
    # Format into 4 groups of 4 characters: XXXX-XXXX-XXXX-XXXX
    hwid = f"{h[0:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"
    _CACHED_HWID = hwid
    return hwid

def decode_and_verify_key(key_str: str, current_hwid: str = None):
    """
    Decode, verify checksum signature, and check HWID matching of a license key string.
    """
    key_str = key_str.strip()
    if not key_str.startswith("SRLIC."):
        return False, "Invalid license key format (must start with SRLIC.)", None, None

    parts = key_str.split(".")
    if len(parts) != 3:
        return False, "Invalid license key structure.", None, None

    _, payload_b64, sig = parts

    # 1. Verify HMAC signature
    expected_sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False, "License signature verification failed (key is invalid or tampered).", None, None

    # 2. Decode payload
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception as e:
        return False, f"Failed to parse license data: {e}", None, None

    # 3. Check HWID
    if current_hwid is None:
        current_hwid = get_machine_hwid()

    key_hwid = str(payload.get("hwid", "")).strip().upper()
    if key_hwid != current_hwid.upper():
        return False, f"This license key belongs to another machine ({key_hwid}) and cannot be used here.", payload, sig

    # 4. Check Expiry
    now_ts = int(time.time())
    expiry_ts = int(payload.get("expiry_at", 0))
    if expiry_ts > 0 and now_ts > expiry_ts:
        return False, "This license key has already expired.", payload, sig

    return True, "License key is valid.", payload, sig

def _obfuscate_license(data_dict: dict, hwid: str) -> str:
    """Scramble license dictionary into unreadable string using Machine HWID."""
    raw_bytes = json.dumps(data_dict, sort_keys=True).encode("utf-8")
    key_bytes = hashlib.sha256(f"{hwid}:{SECRET_KEY.decode('utf-8')}".encode("utf-8")).digest()
    encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw_bytes))
    return base64.b64encode(encrypted).decode("utf-8")

def _deobfuscate_license(encoded_str: str, hwid: str) -> dict:
    """Decode machine-obfuscated license string."""
    encrypted = base64.b64decode(encoded_str.encode("utf-8"))
    key_bytes = hashlib.sha256(f"{hwid}:{SECRET_KEY.decode('utf-8')}".encode("utf-8")).digest()
    raw_bytes = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encrypted))
    return json.loads(raw_bytes.decode("utf-8"))

def save_license_file(payload: dict, signature: str):
    """Save verified license payload and signature to %LOCALAPPDATA%\\salesregister\\license.lic in obfuscated format."""
    os.makedirs(LICENSE_DIR, exist_ok=True)
    hwid = str(payload.get("hwid", "")).strip().upper() or get_machine_hwid()
    
    data = {
        "payload": payload,
        "signature": signature,
        "last_seen_time": int(time.time())
    }
    
    encoded_blob = _obfuscate_license(data, hwid)
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        f.write(encoded_blob)

def read_and_validate_local_license(current_hwid: str = None):
    """
    Inspect the local license file in %LOCALAPPDATA%\\salesregister\\license.lic
    Returns (is_valid, status_code, message, payload)
    """
    if current_hwid is None:
        current_hwid = get_machine_hwid()

    if not os.path.exists(LICENSE_FILE):
        return False, "missing", "No active license found on this machine.", None

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            raw_content = f.read().strip()
            
        # Support both obfuscated blob and legacy JSON if present
        if raw_content.startswith("{"):
            data = json.loads(raw_content)
        else:
            data = _deobfuscate_license(raw_content, current_hwid)
    except Exception as e:
        return False, "corrupted", f"License file is damaged or unreadable: {e}", None

    payload = data.get("payload")
    sig = data.get("signature")
    last_seen = data.get("last_seen_time", 0)

    if not payload or not sig:
        return False, "corrupted", "License file structure is invalid.", None

    # 1. Verify HMAC signature of stored payload
    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8")
    expected_sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return False, "tampered", "License signature mismatch (file was modified).", None

    # 2. Check HWID match
    lic_hwid = str(payload.get("hwid", "")).strip().upper()
    if lic_hwid != current_hwid.upper():
        return False, "invalid_hwid", f"License is registered to a different machine ({lic_hwid}).", payload

    # 3. Check Lifetime vs Demo Expiry & Clock Tamper Checks
    expiry_ts = int(payload.get("expiry_at", 0))
    lic_type = str(payload.get("type", "")).upper()

    # For Lifetime Licenses: ONLY verify cryptographic integrity and machine HWID.
    # No clock tamper detection, no expiry countdown.
    if expiry_ts == 0 or lic_type == "LIFETIME":
        return True, "active", "Lifetime license is active.", payload

    # For Demo / Time-Limited Licenses: Enforce clock rollback detection and expiration limits
    now_ts = int(time.time())
    if last_seen > 0 and (last_seen - now_ts) > 120:
        return False, "clock_rollback", "System clock manipulation detected. Please correct your date and time.", payload

    if now_ts > expiry_ts:
        return False, "expired", "Your license demo/subscription period has expired.", payload

    return True, "active", "License is valid and active.", payload

def get_current_license_status():
    """Returns a full status dictionary for frontend and middleware consumption."""
    current_hwid = get_machine_hwid()
    is_valid, status, msg, payload = read_and_validate_local_license(current_hwid)
    
    expiry_text = "Never (Lifetime)"
    remaining_secs = 0
    lic_type = "NONE"
    client_name = ""

    if payload:
        lic_type = payload.get("type", "DEMO")
        client_name = payload.get("client", "")
        expiry_ts = payload.get("expiry_at", 0)
        if expiry_ts > 0 and lic_type != "LIFETIME":
            now_ts = int(time.time())
            remaining_secs = max(0, expiry_ts - now_ts)
            expiry_text = datetime.fromtimestamp(expiry_ts).strftime("%d-%b-%Y %I:%M:%S %p")
        else:
            expiry_text = "Never (Lifetime)"
            remaining_secs = 999999999

    with _STATE_LOCK:
        _LICENSE_STATE["is_valid"] = is_valid
        _LICENSE_STATE["status"] = status
        _LICENSE_STATE["hwid"] = current_hwid
        _LICENSE_STATE["expiry_text"] = expiry_text
        _LICENSE_STATE["type"] = lic_type
        _LICENSE_STATE["client"] = client_name
        _LICENSE_STATE["remaining_seconds"] = remaining_secs
        _LICENSE_STATE["message"] = msg

    return _LICENSE_STATE.copy()

def update_last_seen_heartbeat():
    """Periodically writes last_seen_time and re-evaluates expiry status only for Demo/Time-limited licenses."""
    current_hwid = get_machine_hwid()
    is_valid, status, msg, payload = read_and_validate_local_license(current_hwid)
    
    expiry_ts = int(payload.get("expiry_at", 0)) if payload else 0
    lic_type = str(payload.get("type", "")).upper() if payload else ""

    # Lifetime licenses do NOT write to disk or track heartbeat
    if is_valid and (expiry_ts > 0 and lic_type != "LIFETIME") and os.path.exists(LICENSE_FILE):
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                raw_content = f.read().strip()
            if raw_content.startswith("{"):
                data = json.loads(raw_content)
            else:
                data = _deobfuscate_license(raw_content, current_hwid)
            data["last_seen_time"] = int(time.time())
            new_blob = _obfuscate_license(data, current_hwid)
            with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                f.write(new_blob)
        except Exception:
            pass

    get_current_license_status()

def _heartbeat_worker():
    """Background worker updating the license state every 2 seconds."""
    while True:
        try:
            update_last_seen_heartbeat()
        except Exception:
            pass
        time.sleep(2)

def start_license_heartbeat():
    """Launch the background heartbeat thread once."""
    global _HEARTBEAT_STARTED
    if not _HEARTBEAT_STARTED:
        _HEARTBEAT_STARTED = True
        t = threading.Thread(target=_heartbeat_worker, daemon=True)
        t.start()

"""Login + session cache for Firstrade's /private/* endpoints.

Reads credentials from environment (or a sibling .env file):

    FIRSTRADE_USERNAME       (required)
    FIRSTRADE_PASSWORD       (required)
    FIRSTRADE_MFA_SECRET     (base32 TOTP seed; only if your account has TOTP)

Supports two MFA flows:
- TOTP: one-shot, requires FIRSTRADE_MFA_SECRET. Used when the /sess/login
  response carries `mfa: true`.
- Email/SMS OTP: two-step. Firstrade sends a 6-digit code to your phone or
  email; you read it and pass it back. Used when /sess/login returns
  `mfa: false` with an `otp` array of channels.

Driven by login.py (request/verify/totp subcommands). positions.py just
loads cached headers via login().

stdlib only.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from _client import ACCESS_TOKEN, BASE_URL

CACHE_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "firstrade-skill"
)
# How long an unverified /sess/request_code result stays usable. Real expiry
# is server-side; 10 min is a conservative client-side guess.
PENDING_TTL = 10 * 60


def load_dotenv(path: Path) -> None:
    """Populate os.environ from a KEY=VALUE file. Does not override existing vars."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


def totp(secret: str, t: float | None = None, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP. `secret` is a base32-encoded seed."""
    key = base64.b32decode(secret.upper().replace(" ", "") + "=" * (-len(secret) % 8))
    counter = int((t if t is not None else time.time()) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def _base_headers() -> dict[str, str]:
    return {"User-Agent": "okhttp/4.9.2", "access-token": ACCESS_TOKEN}


def _request(
    method: str,
    url: str,
    headers: dict[str, str],
    data: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(
        url if url.startswith("http") else f"{BASE_URL}{url}",
        data=body,
        method=method,
    )
    for k, v in headers.items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            raise SystemExit(
                f"HTTP {e.code} on {method} {url}: {raw[:400]!r}"
            ) from e


def _session_path(username: str) -> Path:
    return CACHE_DIR / f"session-{username}.json"


def _pending_path(username: str) -> Path:
    return CACHE_DIR / f"pending-{username}.json"


def _load_session(username: str) -> dict | None:
    p = _session_path(username)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _save_session(username: str, ftat: str, sid: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _session_path(username)
    p.write_text(json.dumps({"ftat": ftat, "sid": sid, "ts": int(time.time())}))
    p.chmod(0o600)


def _load_pending(username: str) -> dict | None:
    p = _pending_path(username)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - d.get("ts", 0) > PENDING_TTL:
        return None
    return d


def _save_pending(
    username: str, t_token: str, verification_sid: str, channel: str, mask: str
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _pending_path(username)
    p.write_text(
        json.dumps(
            {
                "t_token": t_token,
                "verification_sid": verification_sid,
                "channel": channel,
                "mask": mask,
                "ts": int(time.time()),
            }
        )
    )
    p.chmod(0o600)


def _clear_pending(username: str) -> None:
    p = _pending_path(username)
    if p.exists():
        p.unlink()


def _creds() -> tuple[str, str]:
    load_dotenv(Path(__file__).parent / ".env")
    u = os.environ.get("FIRSTRADE_USERNAME", "").strip()
    p = os.environ.get("FIRSTRADE_PASSWORD", "")
    if not u or not p:
        raise SystemExit(
            "Set FIRSTRADE_USERNAME and FIRSTRADE_PASSWORD in your environment, "
            "or in a .env file next to this script."
        )
    return u, p


def _try_cached_session(username: str, password: str) -> dict[str, str] | None:
    """Re-POST /sess/login using the cached ftat to skip MFA and obtain a fresh sid.

    Firstrade rotates `sid` on every login (mobile, web, CLI all share the same
    per-account session counter), so caching sid across processes is futile.
    ftat is the long-lived bearer; sid must be refreshed each invocation.
    Mirrors the upstream `firstrade` package's behaviour.
    """
    cached = _load_session(username)
    if not cached or not cached.get("ftat"):
        return None
    h = _base_headers()
    h["ftat"] = cached["ftat"]
    resp = _request("POST", "/sess/login", h, {"username": username, "password": password})
    # Valid cached ftat → response carries ftat+sid directly, no MFA gating.
    if resp.get("error") or "ftat" not in resp or "sid" not in resp:
        return None
    if resp.get("mfa") or resp.get("otp"):
        # ftat was rejected — server wants a full MFA round.
        return None
    _save_session(username, resp["ftat"], resp["sid"])
    return {**_base_headers(), "ftat": resp["ftat"], "sid": resp["sid"]}


def _post_login(username: str, password: str) -> dict:
    return _request(
        "POST", "/sess/login", _base_headers(), {"username": username, "password": password}
    )


# --- public API used by login.py and positions.py -----------------------------


def do_totp_login() -> None:
    """One-shot login using FIRSTRADE_MFA_SECRET. Only works if the account has TOTP."""
    u, p = _creds()
    secret = os.environ.get("FIRSTRADE_MFA_SECRET", "").strip()
    if not secret:
        raise SystemExit("FIRSTRADE_MFA_SECRET not set; TOTP login unavailable.")
    resp = _post_login(u, p)
    if resp.get("error"):
        raise SystemExit(f"Login failed: {resp['error']}")
    if not resp.get("mfa"):
        raise SystemExit(
            "Account is not configured for TOTP (login returned mfa:false). "
            "Use email/SMS OTP instead: `./login.py request email`."
        )
    verify = _request(
        "POST",
        "/sess/verify_pin",
        _base_headers(),
        {"mfaCode": totp(secret), "remember_for": "30", "t_token": resp["t_token"]},
    )
    if verify.get("error"):
        raise SystemExit(f"TOTP verification failed: {verify['error']}")
    _save_session(u, verify["ftat"], verify["sid"])


def do_request_otp(channel: str) -> dict:
    """Step 1 of the email/SMS OTP flow: ask Firstrade to send a code."""
    u, p = _creds()
    resp = _post_login(u, p)
    if resp.get("error"):
        raise SystemExit(f"Login failed: {resp['error']}")
    if resp.get("mfa"):
        raise SystemExit(
            "Account uses TOTP MFA (mfa:true). Use `./login.py totp` instead "
            "(requires FIRSTRADE_MFA_SECRET)."
        )
    t_token = resp.get("t_token")
    options = resp.get("otp") or []
    pick = next((o for o in options if o.get("channel") == channel), None)
    if not pick:
        avail = [o.get("channel") for o in options]
        raise SystemExit(
            f"No '{channel}' OTP option on this account. Available: {avail}"
        )
    rc = _request(
        "POST",
        "/sess/request_code",
        _base_headers(),
        {"recipientId": pick["recipientId"], "t_token": t_token},
    )
    if rc.get("error"):
        raise SystemExit(f"request_code failed: {rc['error']}")
    vsid = rc.get("verificationSid")
    if not vsid:
        raise SystemExit(f"request_code response missing verificationSid: {rc}")
    _save_pending(u, t_token, vsid, channel, pick["recipientMask"])
    return {"channel": channel, "recipient": pick["recipientMask"]}


def do_verify_otp(code: str) -> None:
    """Step 2 of the email/SMS OTP flow: submit the code the user received."""
    u, _ = _creds()
    pending = _load_pending(u)
    if not pending:
        raise SystemExit(
            "No active pending login (or it expired after 10 min). "
            "Run `./login.py request email` to start over."
        )
    verify = _request(
        "POST",
        "/sess/verify_pin",
        _base_headers(),
        {
            "otpCode": code,
            "verificationSid": pending["verification_sid"],
            "remember_for": "30",
            "t_token": pending["t_token"],
        },
    )
    if verify.get("error"):
        raise SystemExit(f"Verification failed: {verify['error']}")
    _save_session(u, verify["ftat"], verify["sid"])
    _clear_pending(u)


def status() -> str:
    """Human-readable view of the cached session + any pending login."""
    load_dotenv(Path(__file__).parent / ".env")
    u = os.environ.get("FIRSTRADE_USERNAME", "").strip() or "(FIRSTRADE_USERNAME not set)"
    lines = [f"User:    {u}"]
    if u.startswith("("):
        return "\n".join(lines)
    s = _load_session(u)
    if s:
        age = int(time.time() - s.get("ts", 0))
        lines.append(
            f"Session: cached (age {age//3600}h{(age%3600)//60}m, "
            f"ftat={s['ftat'][:8]}…)"
        )
    else:
        lines.append("Session: not cached — run `./login.py request email`")
    pending = _load_pending(u)
    if pending:
        rem = PENDING_TTL - (int(time.time()) - pending["ts"])
        lines.append(
            f"Pending: {pending['channel']} to {pending['mask']}, "
            f"expires in {rem//60}m{rem%60}s — run `./login.py verify <code>`"
        )
    else:
        lines.append("Pending: none")
    return "\n".join(lines)


def login() -> dict[str, str]:
    """Return headers ready for /private/* calls. Used by positions.py.

    Re-POSTs /sess/login with the cached ftat to obtain a fresh sid (sid is
    per-login, not durable across processes). If no valid ftat is cached,
    prints next-step instructions and exits — never blocks on interactive input.
    """
    u, p = _creds()
    h = _try_cached_session(u, p)
    if h is not None:
        return h
    raise SystemExit(
        "No valid cached session. Run the login flow first:\n"
        "  ./login.py request email     (or `request sms`, or `totp`)\n"
        "  ./login.py verify <code>     (after you receive the code)\n"
        "Then re-run this command."
    )


def authed_get(path: str, headers: dict[str, str]) -> dict:
    return _request("GET", path, headers)

"""Shared HTTP client for Firstrade's public mobile-app API.

stdlib-only. The access-token below is the same one the Firstrade Android
app ships with — it's required on every request but no session/login is
needed for /public/* endpoints.
"""
import json
import urllib.request

ACCESS_TOKEN = "833w3XuIFycv18ybi"
BASE_URL = "https://api3x.firstrade.com"

HEADERS = {
    "User-Agent": "okhttp/4.9.2",
    "access-token": ACCESS_TOKEN,
}


def get_json(path: str, timeout: int = 10) -> dict:
    """GET a /public/* path and return parsed JSON.

    `path` may be a leading-slash path (joined with BASE_URL) or a full URL.
    Raises urllib.error.URLError on network failure; caller decides handling.
    """
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

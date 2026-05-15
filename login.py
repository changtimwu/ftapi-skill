#!/usr/bin/env python3
"""One-time login to Firstrade /private/* endpoints.

After a successful run, the session is cached at
~/.config/firstrade-skill/session-<user>.json and reused for ~30 days, so
positions.py (and other private-endpoint scripts) just work without re-login.

Credentials are read from FIRSTRADE_USERNAME / FIRSTRADE_PASSWORD (env or
.env file).

Subcommands:
    status                         show current session/pending-login state
    totp                           one-shot login using FIRSTRADE_MFA_SECRET
    request email|sms              ask Firstrade to send a 6-digit code
    verify CODE                    finish login with the code you received
"""
import argparse
import sys

from _auth import do_request_otp, do_totp_login, do_verify_otp, status


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show cached session + pending-login state")
    sub.add_parser("totp", help="log in via TOTP (needs FIRSTRADE_MFA_SECRET)")
    p_req = sub.add_parser("request", help="ask Firstrade to send an OTP code")
    p_req.add_argument(
        "channel", choices=["email", "sms"], nargs="?", default="email",
        help="where to send the code (default: email)",
    )
    p_ver = sub.add_parser("verify", help="finish login with the OTP code")
    p_ver.add_argument("code", help="the 6-digit code from email/SMS")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(status())
    elif args.cmd == "totp":
        do_totp_login()
        print("TOTP login complete. Session cached.")
    elif args.cmd == "request":
        r = do_request_otp(args.channel)
        print(f"Code sent via {r['channel']} to {r['recipient']}.")
        print(f"When you have it, run: ./login.py verify <code>")
        print("(Code expires in ~10 minutes.)")
    elif args.cmd == "verify":
        do_verify_otp(args.code)
        print("Login complete. Session cached — positions.py will now work.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

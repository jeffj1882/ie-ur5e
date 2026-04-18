#!/usr/bin/env python3
"""Block until URSim is accepting Dashboard connections.

Polls TCP :29999 with the Dashboard Server `robotmode` command. A valid reply
starts with "Robotmode:" per the UR Dashboard manual.

Exit 0 on readiness, 1 on timeout.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time


def dashboard_probe(host: str, port: int, timeout: float = 1.5) -> str | None:
    """Open a socket, send `robotmode`, return the reply (or None on failure)."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            # Drain the banner ("Connected: Universal Robots Dashboard Server\n")
            _ = sock.recv(4096)
            sock.sendall(b"robotmode\n")
            data = sock.recv(4096)
            return data.decode("ascii", errors="replace").strip() or None
    except (OSError, socket.timeout):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Wait for URSim Dashboard readiness")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=29999)
    ap.add_argument("--timeout", type=float, default=120.0, help="overall budget, seconds")
    ap.add_argument("--interval", type=float, default=2.0, help="poll interval, seconds")
    args = ap.parse_args()

    deadline = time.monotonic() + args.timeout
    print(
        f"Waiting for URSim Dashboard at {args.host}:{args.port} "
        f"(timeout {args.timeout:.0f}s)",
        flush=True,
    )

    last_err = "no response"
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        reply = dashboard_probe(args.host, args.port)
        if reply and reply.lower().startswith("robotmode:"):
            print(f"URSim ready — {reply} (after {attempts} probes)")
            return 0
        last_err = reply or "connection refused / no banner"
        print(f"  [{attempts:3d}] not ready: {last_err[:60]}", flush=True)
        time.sleep(args.interval)

    print(
        f"ERROR: URSim did not become ready within {args.timeout:.0f}s "
        f"(last response: {last_err!r})",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

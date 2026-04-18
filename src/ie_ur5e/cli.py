"""Console-script entry points."""

from __future__ import annotations

import argparse
import asyncio
import sys

from ie_ur5e import __version__
from ie_ur5e.connection import load_config, resolve_host
from ie_ur5e.dashboard import DashboardClient, DashboardError


def check() -> int:
    """Smoke check: import every module, load config, print summary."""
    from ie_ur5e import api as _api  # noqa: F401
    from ie_ur5e import dashboard as _d  # noqa: F401
    from ie_ur5e import motion as _m  # noqa: F401
    from ie_ur5e import safety as _s  # noqa: F401

    cfg = load_config()
    print(f"ie-ur5e {__version__}")
    print(f"  host_ip        = {cfg.host_ip}")
    print(f"  rtde_frequency = {cfg.rtde_frequency}")
    print(f"  payload_kg     = {cfg.payload_kg}")
    print(f"  home_joints    = {cfg.home_joints_rad}")
    return 0


def api() -> int:
    """Run the FastAPI control panel on 127.0.0.1:8080."""
    import uvicorn

    uvicorn.run("ie_ur5e.api:app", host="127.0.0.1", port=8080, log_level="info")
    return 0


# ── Dashboard CLI ──────────────────────────────────────────────────────────
_DASH_COMMANDS: dict[str, str] = {
    "robotmode": "Print the controller robotmode (e.g. IDLE, POWER_OFF).",
    "safetystatus": "Print safetystatus (NORMAL, PROTECTIVE_STOP, ...).",
    "power-on": "Power on the robot.",
    "power-off": "Power off the robot.",
    "brake-release": "Release the joint brakes (robot must be powered on).",
    "unlock-protective-stop": "Clear an active protective stop.",
    "popup": "Show a popup on the pendant. Usage: popup <message>",
    "close-popup": "Dismiss any popup.",
    "play": "Play the currently loaded program.",
    "stop": "Stop the program.",
    "pause": "Pause the program.",
    "load": "Load a URP. Usage: load <path-in-container>",
    "get-loaded-program": "Print the path of the currently-loaded URP.",
    "is-in-remote-control": "Print 'true' if robot is in remote control.",
}


def _make_dash_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ie-ur5e-dash", description="UR Dashboard CLI")
    p.add_argument("--host", help="Override ROBOT_IP / config host_ip")
    p.add_argument("--port", type=int, default=29999)
    p.add_argument("--timeout", type=float, default=5.0)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, desc in _DASH_COMMANDS.items():
        s = sub.add_parser(name, help=desc)
        if name == "popup":
            s.add_argument("message", nargs="+", help="Text to display")
        elif name == "load":
            s.add_argument("program", help="URP file path (as seen inside URSim container)")
    return p


async def _run_dash(args: argparse.Namespace) -> int:
    host = resolve_host(args.host)
    try:
        async with DashboardClient(host, port=args.port, timeout=args.timeout) as c:
            match args.cmd:
                case "robotmode":
                    print((await c.robotmode()).value)
                case "safetystatus":
                    print((await c.safetystatus()).value)
                case "power-on":
                    print(await c.power_on())
                case "power-off":
                    print(await c.power_off())
                case "brake-release":
                    print(await c.brake_release())
                case "unlock-protective-stop":
                    print(await c.unlock_protective_stop())
                case "popup":
                    print(await c.popup(" ".join(args.message)))
                case "close-popup":
                    print(await c.close_popup())
                case "play":
                    print(await c.play())
                case "stop":
                    print(await c.stop())
                case "pause":
                    print(await c.pause())
                case "load":
                    print(await c.load(args.program))
                case "get-loaded-program":
                    result = await c.get_loaded_program()
                    print(result if result is not None else "(none)")
                case "is-in-remote-control":
                    print("true" if await c.is_in_remote_control() else "false")
    except DashboardError as e:
        print(f"ERROR: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: connection failed: {e}", file=sys.stderr)
        return 3
    return 0


def dash() -> int:
    args = _make_dash_parser().parse_args()
    return asyncio.run(_run_dash(args))

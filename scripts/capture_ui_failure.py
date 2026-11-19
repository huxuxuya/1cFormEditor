#!/usr/bin/env python3
"""Capture the active native TestClient window for one failed UI scenario."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from PIL import ImageGrab


def _run(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=3).stdout


def _client_window(pid):
    tree = _run("xwininfo", "-root", "-tree")
    matches = []
    for match in re.finditer(r"(?m)^\s+(0x[0-9a-fA-F]+)\s+\"([^\"]*)\"", tree):
        window_id, title = match.groups()
        try:
            properties = _run("xprop", "-id", window_id, "_NET_WM_PID")
            if not re.search(r"_NET_WM_PID\(CARDINAL\)\s*=\s*" + str(pid) + r"\b", properties):
                continue
            info = _run("xwininfo", "-id", window_id)
        except subprocess.CalledProcessError:
            continue
        if "Map State: IsViewable" not in info:
            continue
        values = {}
        for key in ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height"):
            value = re.search(r"(?m)^\s*" + re.escape(key) + r":\s*(-?\d+)", info)
            if value:
                values[key] = int(value.group(1))
        if len(values) != 4 or values["Width"] < 64 or values["Height"] < 64:
            continue
        matches.append((window_id, title, values))
    if not matches:
        raise RuntimeError(f"No visible X11 window belongs to TestClient pid {pid}")
    # The main application form is the largest visible top-level window owned by TestClient.
    return max(matches, key=lambda item: item[2]["Width"] * item[2]["Height"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-pid", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenario-id", required=True)
    args = parser.parse_args()

    try:
        manifest_path = Path(__file__).resolve().parents[1] / "tests" / "ui-scenarios.json"
        allowed_ids = {item["id"] for item in json.loads(manifest_path.read_text(encoding="utf-8"))["scenarios"]}
        if args.scenario_id not in allowed_ids or not re.fullmatch(r"[A-Za-z0-9_-]+", args.scenario_id):
            raise ValueError("Unknown UI scenario id")
        output_dir = args.output_dir.resolve(strict=True)
        if output_dir.parts[-3:] != ("reports", "ui-cf", "screenshots"):
            raise ValueError("Screenshot output must be reports/ui-cf/screenshots")
        if args.client_pid <= 1:
            raise ValueError("Invalid TestClient process id")

        window_id, title, geometry = _client_window(args.client_pid)
        x = geometry["Absolute upper-left X"]
        y = geometry["Absolute upper-left Y"]
        width = geometry["Width"]
        height = geometry["Height"]
        display = os.environ.get("DISPLAY")
        if not display:
            raise RuntimeError("DISPLAY is not set for the TestClient Xvfb")
        image = ImageGrab.grab(xdisplay=display, bbox=(x, y, x + width, y + height))
        image.save(output_dir / f"{args.scenario_id}.png", format="PNG")
        (output_dir / f"{args.scenario_id}.capture-error.txt").unlink(missing_ok=True)
        print(f"Captured {args.scenario_id} from TestClient window {window_id} ({title})")
        return 0
    except Exception as error:
        try:
            output_dir = args.output_dir.resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{args.scenario_id}.capture-error.txt").write_text(
                str(error)[:2000] + "\n", encoding="utf-8")
        except Exception:
            pass
        print(f"Could not capture TestClient screenshot: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

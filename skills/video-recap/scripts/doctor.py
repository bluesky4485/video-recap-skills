#!/usr/bin/env python3
"""Lightweight environment doctor for the video-recap skill."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from config import CONFIG, normalize_api_url


SCRIPT_DIR = Path(__file__).resolve().parent


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def _check_tts_smoke(voice: str) -> dict[str, object]:
    if not _command_exists("edge-tts"):
        return {"ok": False, "skipped": True, "reason": "edge-tts not found"}
    if not _command_exists("ffprobe"):
        return {"ok": False, "skipped": True, "reason": "ffprobe not found"}
    with tempfile.TemporaryDirectory(prefix="video-recap-tts-smoke-") as tmp:
        media = Path(tmp) / "smoke.mp3"
        result = _run([
            "edge-tts",
            "--voice", voice,
            "--text", "测试一下。",
            "--write-media", str(media),
        ], timeout=60)
        if result.returncode != 0:
            return {"ok": False, "error": (result.stderr or result.stdout)[-500:]}
        probe = _run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(media),
        ])
        try:
            duration = float(probe.stdout.strip())
        except (TypeError, ValueError):
            duration = 0.0
        return {"ok": duration > 0, "duration": duration}


def build_report(*, tts_smoke: bool = False) -> dict[str, object]:
    api_url = normalize_api_url(CONFIG.get("api_url"))
    checks: dict[str, object] = {
        "system_tools": {
            "ffmpeg": _command_exists("ffmpeg"),
            "ffprobe": _command_exists("ffprobe"),
        },
        "tts": {
            "edge_tts_command": _command_exists("edge-tts"),
            "edge_tts_module": importlib.util.find_spec("edge_tts") is not None,
            "default_voice": CONFIG.get("edge_tts_voice"),
        },
        "api_config": {
            "openai_api_url": api_url,
            "openai_api_key_set": bool(CONFIG.get("api_key")),
            "openai_model": CONFIG.get("vlm_model"),
        },
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
    }
    if tts_smoke:
        checks["tts_smoke"] = _check_tts_smoke(str(CONFIG.get("edge_tts_voice") or "zh-CN-YunxiNeural"))

    failures: list[str] = []
    tools = checks["system_tools"]  # type: ignore[index]
    for name, ok in tools.items():  # type: ignore[union-attr]
        if not ok:
            failures.append(f"Missing system tool: {name}")
    tts = checks["tts"]  # type: ignore[index]
    if not (tts.get("edge_tts_command") or tts.get("edge_tts_module")):  # type: ignore[union-attr]
        failures.append("Missing edge-tts; install with `pip3 install edge-tts`")
    if tts_smoke and not checks.get("tts_smoke", {}).get("ok"):  # type: ignore[union-attr]
        failures.append("edge-tts smoke test failed")
    if not checks["api_config"].get("openai_api_key_set"):  # type: ignore[union-attr]
        failures.append("OPENAI_API_KEY is not set; VLM analysis will fail")
    return {
        "ok": not failures,
        "repo_root": str(SCRIPT_DIR.parents[2]),
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check video-recap runtime prerequisites.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--tts-smoke", action="store_true", help="Run a short edge-tts synthesis test")
    args = parser.parse_args()

    report = build_report(tts_smoke=args.tts_smoke)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("video-recap doctor")
    print(f"Repo root: {report['repo_root']}")
    for section, values in report["checks"].items():
        print(f"\n[{section}]")
        if isinstance(values, dict):
            for key, value in values.items():
                print(f"- {key}: {value}")
        else:
            print(values)
    if report["failures"]:
        print("\nStatus: FAILED")
        for failure in report["failures"]:
            print(f"- {failure}")
        return 1
    print("\nStatus: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

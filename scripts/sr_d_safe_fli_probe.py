from __future__ import annotations

from importlib.metadata import distribution, version
import json
from pathlib import Path
import subprocess

UA = "CheapFlightRadar/0.1 (+public-research; no-proxy)"


def patch_transport() -> dict[str, int]:
    root = Path(distribution("flights").locate_file("fli"))
    client = root / "search" / "client.py"
    flights = root / "search" / "flights.py"
    dates = root / "search" / "dates.py"

    client_text = client.read_text(encoding="utf-8")
    retry_before = client_text.count("stop_after_attempt(3)")
    if retry_before < 2:
        raise RuntimeError(f"unexpected fli retry source shape: {retry_before}")
    client_text = client_text.replace("stop_after_attempt(3)", "stop_after_attempt(1)")
    marker = '"content-type": "application/x-www-form-urlencoded;charset=UTF-8",'
    if marker not in client_text:
        raise RuntimeError("fli client header marker not found")
    client_text = client_text.replace(marker, marker + f'\n        "user-agent": "{UA}",', 1)
    client.write_text(client_text, encoding="utf-8")

    removed = 0
    for path in (flights, dates):
        text = path.read_text(encoding="utf-8")
        count = text.count('impersonate="chrome",')
        if count < 1:
            raise RuntimeError(f"expected browser impersonation call not found in {path.name}")
        text = text.replace('            impersonate="chrome",\n', "")
        path.write_text(text, encoding="utf-8")
        removed += count

    verify_client = client.read_text(encoding="utf-8")
    verify_flights = flights.read_text(encoding="utf-8")
    verify_dates = dates.read_text(encoding="utf-8")
    if "stop_after_attempt(3)" in verify_client:
        raise RuntimeError("automatic 3-attempt retry remains")
    if 'impersonate="chrome"' in verify_flights or 'impersonate="chrome"' in verify_dates:
        raise RuntimeError("browser impersonation remains")
    if UA not in verify_client:
        raise RuntimeError("fixed CFR user-agent was not installed")
    return {"retry_decorators_reduced_to_one_attempt": retry_before, "impersonate_calls_removed": removed}


def run(name: str, args: list[str]) -> dict[str, object]:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=180, check=False)
        return {
            "surface": name,
            "returncode": cp.returncode,
            "stdout": cp.stdout[-12000:],
            "stderr": cp.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "surface": name,
            "returncode": 124,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": "timeout",
        }


def main() -> None:
    patch = patch_transport()
    probes = [
        run(
            "exact_round_trip",
            [
                "fli", "flights", "TPE", "NRT", "2026-10-05",
                "--return", "2026-10-09", "--currency", "TWD",
                "--language", "zh-TW", "--country", "TW", "--format", "json",
            ],
        ),
        run(
            "flexible_dates",
            [
                "fli", "dates", "TPE", "NRT", "--from", "2026-10-01",
                "--to", "2026-10-31", "--duration", "4", "--round",
                "--currency", "TWD", "--language", "zh-TW", "--country", "TW",
                "--format", "json",
            ],
        ),
    ]
    print(
        "SR_D_RESULT="
        + json.dumps(
            {
                "flights_version": version("flights"),
                "transport": {
                    "user_agent": UA,
                    "proxy": "none/default_direct",
                    "browser_impersonation": "removed_before_import",
                    "retry_attempts": 1,
                    "patch_assertions": patch,
                },
                "probes": probes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app

UNITS = ("fetch.service", "import.service", "analysis.service", "build.service")


def _systemctl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"
    stub = bin_dir / "systemctl"
    stub.write_text(f'#!/bin/sh\necho "$*" >> {log}\n{body}\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return log


def _config(tmp_path: Path, build_report: Path) -> Path:
    config = tmp_path / "refresh.toml"
    units = ", ".join(f'"{unit}"' for unit in UNITS)
    config.write_text(
        f'[refresh]\nunits = [{units}]\nreport_file = "{tmp_path / "refresh.json"}"\n'
        f'[refresh.reports]\n"build.service" = "{build_report}"\n'
    )
    return config


def test_refresh_stops_at_a_failed_step_and_reports_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _systemctl(
        tmp_path,
        monkeypatch,
        'case "$*" in\n'
        '  "start analysis.service") echo "Job failed: VM stopped" >&2; exit 1;;\n'
        '  "show --property=Result --value analysis.service") echo exit-code;;\n'
        "esac",
    )
    result = CliRunner().invoke(
        app, ["refresh", "--config", str(_config(tmp_path, tmp_path / "b"))]
    )

    assert result.exit_code == 1
    assert [line.split()[-1] for line in log.read_text().splitlines() if "start" in line] == [
        "fetch.service",
        "import.service",
        "analysis.service",
    ]
    report = json.loads((tmp_path / "refresh.json").read_text())
    assert report["status"] == "failed"
    assert [step["status"] for step in report["steps"]] == [
        "succeeded",
        "succeeded",
        "failed",
        "skipped",
    ]
    assert report["steps"][2]["detail"] == "result=exit-code; Job failed: VM stopped"


def test_refresh_reports_a_partial_build_with_its_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = tmp_path / "build.json"
    document = {
        "status": "partial",
        "formats": [
            {"format": "engine", "previous": "g1", "generation": "g2", "error": None},
            {"format": "pioneer", "previous": "p1", "generation": None, "error": "opus"},
        ],
    }
    _systemctl(
        tmp_path,
        monkeypatch,
        f'case "$*" in "start build.service")'
        f" echo '{json.dumps(document)}' > {build}; exit 1;; esac",
    )
    result = CliRunner().invoke(app, ["refresh", "--config", str(_config(tmp_path, build))])

    assert result.exit_code == 1
    assert "format=pioneer failed previous=p1 detail=opus" in result.output
    assert "SUMMARY status=partial" in result.output
    report = json.loads((tmp_path / "refresh.json").read_text())
    assert report["steps"][-1]["report"]["formats"][0]["generation"] == "g2"


def test_refresh_ignores_a_report_left_by_an_earlier_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = tmp_path / "build.json"
    build.write_text(json.dumps({"status": "partial", "formats": []}))
    os.utime(build, (0, 0))
    _systemctl(tmp_path, monkeypatch, "exit 0")
    result = CliRunner().invoke(app, ["refresh", "--config", str(_config(tmp_path, build))])

    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "refresh.json").read_text())["steps"][-1]["report"] is None

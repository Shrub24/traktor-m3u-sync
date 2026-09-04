"""JSON run reports for completed import and export commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .contracts import AdapterWarning, SyncResult
from .fs import write_atomic

REPORT_WRITE_FAILED: str = "report_write_failed"


def utc_now() -> str:
    """Current UTC time as an ISO-8601 timestamp with second precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_run_report(
    path: Path,
    *,
    command: str,
    format: str,
    started: str,
    finished: str,
    result: SyncResult | None,
    exit_status: int,
    error: AdapterWarning | None = None,
    dry_run: bool = False,
) -> AdapterWarning | None:
    """Serialize one completed run to JSON, creating parent directories as needed.

    A hard failure (``result`` None) still writes a truthful report: the true
    ``exit_status``, whatever counts exist, and the error as a structured warning
    entry. A write failure returns a structured warning instead of raising, so the
    caller's exit status is never changed by a report problem.
    """
    try:
        document = _document(
            command=command,
            format=format,
            started=started,
            finished=finished,
            result=result,
            exit_status=exit_status,
            error=error,
            dry_run=dry_run,
        )
        payload = json.dumps(document, indent=2) + "\n"
        write_atomic(path.expanduser(), payload.encode("utf-8"))
    except Exception as exc:
        return AdapterWarning(
            code=REPORT_WRITE_FAILED,
            message="Failed to write the run report",
            detail=f"{path}: {exc}",
        )
    return None


def _document(
    *,
    command: str,
    format: str,
    started: str,
    finished: str,
    result: SyncResult | None,
    exit_status: int,
    error: AdapterWarning | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    warnings = [_warning_doc(warning) for warning in result.warnings] if result is not None else []
    if error is not None:
        warnings.append(_warning_doc(error))
    document: dict[str, object] = {
        "command": command,
        "format": format,
        "started": started,
        "finished": finished,
        "counts": dict(result.counts) if result is not None else {},
        "warnings": warnings,
        "exit_status": exit_status,
    }
    if dry_run:
        document["dry_run"] = True
    if result is not None and result.provenance is not None:
        document["provenance"] = {
            "source_format": result.provenance.source_format,
            "imported_at": result.provenance.imported_at,
        }
    return document


def _warning_doc(warning: AdapterWarning) -> dict[str, str]:
    document = {"code": warning.code, "message": warning.message}
    if warning.playlist is not None:
        document["playlist"] = warning.playlist
    if warning.detail is not None:
        document["detail"] = warning.detail
    return document

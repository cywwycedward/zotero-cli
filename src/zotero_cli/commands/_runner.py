"""commands/_runner.py -- shared CLI command runner (commands-layer infra).

Per DEVELOPMENT.md §5.2: this module is allowed to call sys.exit and write
stdout/stderr because it serves the CLI command path. utils/ is not.

GlobalOptions (ctx.obj contract) + run_command (timing, error capture,
stdout/stderr split per design §7.5).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from zotero_cli.models.envelope import Envelope
from zotero_cli.models.errors import CLIError, MutuallyExclusiveArgsError

# Import as module attribute so tests can monkeypatch
# zotero_cli.commands._runner._output.render without re-import.
from zotero_cli.utils import output as _output


@dataclass
class GlobalOptions:
    profile: str = "default"
    json_mode: bool = False
    quiet: bool = False
    config_path: Path | None = None


def run_command(
    *,
    command: str,
    mode: _output.OutputMode,
    options: GlobalOptions,
    work: Callable[[], Any],
    meta_extra: dict[str, Any] | None = None,
    field_filter: list[str] | None = None,
) -> NoReturn:
    # 1) Global mutex (design §7.2)
    if options.json_mode and options.quiet:
        err = MutuallyExclusiveArgsError(
            "--json and --quiet cannot be combined",
            hint="Use --json for full envelope, --quiet for affected_keys only.",
        )
        emit_failure(err, command, 0, options)
        sys.exit(err.exit_code)

    # 2) Mode-specific quiet check (design §7.2 table)
    if options.quiet and mode in (_output.OutputMode.YAML, _output.OutputMode.JSON):
        err = MutuallyExclusiveArgsError(
            f"--quiet is not supported for {mode.value} output",
            hint="Use --json for machine-readable output instead.",
        )
        emit_failure(err, command, 0, options)
        sys.exit(err.exit_code)

    # 3) Call service
    start = time.perf_counter()
    try:
        data = work()
    except CLIError as err:
        elapsed = int((time.perf_counter() - start) * 1000)
        emit_failure(err, command, elapsed, options)
        sys.exit(err.exit_code)

    elapsed = int((time.perf_counter() - start) * 1000)

    # 4) Render -- render() can also raise CLIError (render-side validation),
    #    so catch and route as envelope failure.
    try:
        env = Envelope.success(
            data=data,
            command=command,
            elapsed_ms=elapsed,
            meta_extra=meta_extra,
        )
        out = _output.render(
            envelope=env,
            mode=mode,
            json_mode=options.json_mode,
            quiet=options.quiet,
            field_filter=field_filter,
        )
    except CLIError as err:
        emit_failure(err, command, elapsed, options)
        sys.exit(err.exit_code)

    if out:
        sys.stdout.write(out)
    sys.exit(0)


def emit_failure(
    err: CLIError,
    command: str,
    elapsed_ms: int,
    options: GlobalOptions,
) -> None:
    """Public helper: render an envelope failure and write to the right stream.

    Used by run_command and by special command paths (e.g. items export) that
    don't go through run_command but still need design §7.5 stdout/stderr split.

    Caller is responsible for calling sys.exit(err.exit_code) afterward.
    """
    try:
        env = Envelope.failure(err, command=command, elapsed_ms=elapsed_ms)
        out = _output.render(
            envelope=env,
            mode=_output.OutputMode.KV,
            json_mode=options.json_mode,
            quiet=False,
        )
    except Exception:  # pragma: no cover -- defense in depth
        if options.json_mode:
            import json as _json

            payload = {
                "ok": False,
                "data": None,
                "error": {
                    "code": err.code,
                    "message": err.message,
                    "category": err.category,
                    "hint": err.hint,
                    "context": err.context if err.context else None,
                    "cause": None,
                },
                "meta": {
                    "command": command,
                    "elapsed_ms": elapsed_ms,
                    "exit_code": err.exit_code,
                },
            }
            sys.stdout.write(_json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            sys.stderr.write(f"✗ Error: {err.code}\n  {err.message}\n")
        return
    stream = sys.stdout if options.json_mode else sys.stderr
    stream.write(out)

from __future__ import annotations

import json

import pytest

from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.models.errors import ItemNotFoundError
from zotero_cli.utils.output import OutputMode


def test_success_writes_to_stdout(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(),
            work=lambda: {"key": "ABC", "title": "T"},
        )
    assert ei.value.code == 0
    cap = capsys.readouterr()
    assert "key: ABC" in cap.out
    assert cap.err == ""


def test_default_mode_error_writes_to_stderr(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(json_mode=False),
            work=lambda: (_ for _ in ()).throw(ItemNotFoundError("nope")),
        )
    assert ei.value.code == 1
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "ITEM_NOT_FOUND" in cap.err


def test_json_mode_error_writes_envelope_to_stdout(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(json_mode=True),
            work=lambda: (_ for _ in ()).throw(ItemNotFoundError("nope")),
        )
    assert ei.value.code == 1
    cap = capsys.readouterr()
    assert cap.err == ""
    parsed = json.loads(cap.out)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "ITEM_NOT_FOUND"


def test_quiet_and_json_mutex_raises(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(json_mode=True, quiet=True),
            work=lambda: {"key": "ABC"},
        )
    assert ei.value.code == 64
    cap = capsys.readouterr()
    # json_mode=True => error writes to stdout as JSON envelope
    parsed = json.loads(cap.out)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"


def test_meta_extra_propagates(capsys) -> None:
    with pytest.raises(SystemExit):
        run_command(
            command="items.list",
            mode=OutputMode.KV_LIST,
            options=GlobalOptions(json_mode=True),
            work=lambda: [{"key": "X"}],
            meta_extra={"count": 1, "library_id": "12345"},
        )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["meta"]["count"] == 1
    assert parsed["meta"]["library_id"] == "12345"


def test_yaml_mode_with_quiet_rejected_before_work(capsys, mocker) -> None:
    work_spy = mocker.Mock()
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="config.show",
            mode=OutputMode.YAML,
            options=GlobalOptions(quiet=True),
            work=work_spy,
        )
    assert ei.value.code == 64
    work_spy.assert_not_called()
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "MUTUALLY_EXCLUSIVE_ARGS" in cap.err

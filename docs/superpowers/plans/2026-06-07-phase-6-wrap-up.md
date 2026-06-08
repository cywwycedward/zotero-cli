# 阶段 6:Agent 自省 + 收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**:把阶段 1-5 的子命令拼成完整可执行 CLI(顶级 Typer app + 入口),提供 `schema` 自省命令让 agent 不靠 `--help` 解析就能拿到完整命令树定义,补齐 README,跑完设计 §12.5 手动测试清单,验证全项目覆盖率/mypy/ruff,关项目。

**Architecture**:本阶段不再新增业务模块,只做"装配 + 自省 + 文档 + 验收"。`cli.py` 只引入并组合阶段 2-5 的 `commands.{config,items,collections,tags,feeds}.app` 与本阶段新增的 `commands.schema.app`,同时挂上设计 §6 定义的全局 flag(`--json` / `--profile` / `--quiet`)。`schema` 命令依赖 Typer 暴露的 Click `get_command()` 接口反射命令树,不引入新依赖。

**Tech Stack**:Python 3.11+ / Typer 0.12+ / Click(Typer 内嵌) / pytest。无新增依赖。

**Source-of-truth references**:
- 设计文档:`docs/superpowers/specs/2026-06-07-zotero-cli-design.md`(重点 §6 命令树、§7.2 schema 行、§12.4 覆盖率、§12.5 手动测试)
- 协作规范:`DEVELOPMENT.md`(重点 §6 TDD、§9.6 阶段 6 验收)
- 同期 plan 风格参考:`docs/superpowers/plans/2026-06-07-phase-1-infrastructure.md` Tasks 11-17

---

## 文件结构

```
zotero-cli/
├── README.md                                 # Task 5 完整重写(原阶段 1 占位)
├── DEVELOPMENT.md                            # Task 9 仅在发现设计偏离时改 §12 修订记录
├── src/zotero_cli/
│   ├── __main__.py                           # Task 2 替换阶段 1 占位:def main() -> None
│   ├── cli.py                                # Task 1 新增:顶级 Typer app
│   └── commands/
│       └── schema.py                         # Task 3-4 新增:schema [--command NAME]
└── tests/
    ├── unit/
    │   ├── test_cli.py                       # Task 1
    │   └── test_schema_command.py            # Task 3-4
    └── e2e/
        └── test_invocation_smoke.py          # Task 2(可选)入口冒烟
```

不动其他文件(阶段 1-5 已就位)。

## 模块依赖关系

```
__main__.py  →  cli.py  →  commands.{config,items,collections,tags,feeds,schema}.app
                              ↑
                              schema.py 反射上述各 app 的 Click Command 树
```

**任务执行顺序**:Task 1 → 2 → 3 → 4 → 5(可与 6 并行)→ 6 → 7 → 8 → 9 → 10 → 11(可选)。
Task 1-4 是代码(必须 TDD);5 是文档;6 是手动操作;7-10 是验收闸;11 可选。

---

## Task 1: src/zotero_cli/cli.py — 顶级 Typer app + 全局 flags

**Files:**
- Create: `src/zotero_cli/cli.py`
- Test: `tests/unit/test_cli.py`

设计 §6 定义全局 flag 位于子命令之前:`--json` / `--profile NAME` / `--quiet`(`-q`)。`--json` 与 `--quiet` 互斥。本 Task 只组装 app + 校验互斥并把全局 flag 写入 `ctx.obj`,后续命令通过 `ctx.obj` 取值(阶段 2-5 已经按此约定接 `ctx`)。

**关键测试**(`tests/unit/test_cli.py`):

```python
from __future__ import annotations

import json

import typer
from typer.testing import CliRunner

from zotero_cli.cli import app
from zotero_cli.commands._runner import GlobalOptions

runner = CliRunner(mix_stderr=False)


def test_app_registers_all_subapps() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("items", "collections", "tags", "feeds", "config", "schema"):
        assert sub in result.stdout


def test_json_and_quiet_default_mode_writes_to_stderr() -> None:
    """Mutex 校验由 run_command 在子命令路径上拦截（Phase 2 Task 6b）。
    json_mode=True + quiet=True 是矛盾输入；run_command 第一步抛
    MutuallyExclusiveArgsError。设计 §7.5 要求：

      - 默认模式（这里 json_mode=True 但因为 mutex 触发了错误路径）
        → 错误 envelope 走 stdout（json_mode=True 的承诺：stdout 永远是合法 JSON）。

    所以本测试断言 stdout 是合法 envelope JSON，stderr 为空。"""
    for args in (["--json", "--quiet"], ["--json", "-q"]):
        result = runner.invoke(app, [*args, "items", "list"])
        assert result.exit_code == 64
        assert result.stderr == ""
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is False
        assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"
        assert parsed["meta"]["exit_code"] == 64


def test_quiet_alone_does_not_trigger_mutex_at_top_level() -> None:
    """单独 --quiet 不触发 mutex；只在子命令路径上根据 mode 决定是否拒绝。
    这里用 'items list' 作为 KV_LIST mode（接受 --quiet）→ 走正常路径。"""
    # 注意：本测试不验证 service 行为，只验证 cli.py callback 不自己拦截 --quiet
    result = runner.invoke(app, ["--quiet", "items", "list", "--limit", "0"])
    # 假设 service 返回空列表 → quiet 模式输出 0 字节
    # （依赖 Phase 3 已实现；如本任务先行可改为 mock service）
    assert result.exit_code in (0, 1, 2, 3, 4)  # 任意正常退出码，但不是 64


def _build_callback():
    """重建 cli.py callback 的等价品给本测试用，注入到一个**临时** Typer app。

    不能直接给真 `cli.app` 注册 `__probe` 子命令——CliRunner 是进程内调用，
    模块全局会污染后续 help / schema 测试。这里另起一个 typer.Typer，复用同一份
    callback 函数体（从 cli 模块取），单独注册一个 probe，测完即丢。
    """
    from zotero_cli import cli as cli_module

    sub_app = typer.Typer()
    # 通过 add_typer + 顶层 callback 重新挂一个等价 callback；
    # 直接拿真 callback 函数 cli_module.main 重新注册到新 app。
    sub_app.callback()(cli_module.main)
    return sub_app


def test_global_flags_propagate_to_ctx_obj() -> None:
    """验证 cli.callback 把全局 flags 写进 ctx.obj 为 GlobalOptions。

    用一个**临时** Typer app（不污染真 cli.app），挂同一份 callback，
    再注册一个 probe 子命令读 ctx.obj。"""
    captured: dict[str, GlobalOptions] = {}
    isolated = _build_callback()

    @isolated.command("probe")
    def probe(ctx: typer.Context) -> None:
        captured["opts"] = ctx.obj

    isolated_runner = CliRunner(mix_stderr=False)
    isolated_runner.invoke(isolated, ["--profile", "work", "--json", "probe"])
    assert captured["opts"] == GlobalOptions(json_mode=True, profile="work", quiet=False)

    isolated_runner.invoke(isolated, ["probe"])
    assert captured["opts"] == GlobalOptions(json_mode=False, profile="default", quiet=False)


def test_real_app_does_not_have_probe() -> None:
    """显式回归：真 cli.app 没被前一个测试污染，不含 'probe' 子命令。"""
    result = runner.invoke(app, ["--help"])
    assert "probe" not in result.stdout
```

> **回应 review P2 Issue 4（测试污染全局 app）**：原版直接 `@app.command("__probe")` 注册到 `cli.app`，CliRunner 是进程内调用、不会隔离模块全局——`__probe` 会留在 app 里被后续 `--help` / `schema` 等测试看见，导致测试顺序敏感。修订后：① 拆 `_build_callback()` helper 起一个临时 Typer app 复用同一份 callback；② probe 注册到临时 app，测完即丢；③ 新增 `test_real_app_does_not_have_probe` 显式回归，确认真 `cli.app` 不被污染。

> **回应 review P1 Issue 2（顶层 mutex 测试与 runner 冲突）**：原版断言 stderr 含 `MUTUALLY_EXCLUSIVE_ARGS`，但 cli.py callback 不自己拦截 mutex（已委托给 run_command）；run_command 在 `json_mode=True` 时把 envelope 写 stdout（设计 §7.5）。两者冲突。修订后：
>
> - `cli.py` callback 仅构造 `GlobalOptions` 放 `ctx.obj`，不做 mutex 校验；
> - 测试改成：`--json --quiet` 走完 callback 进 `items list` 路径，由 run_command 拦截 → envelope JSON 到 stdout；测试解析 stdout JSON 验证 `error.code == "MUTUALLY_EXCLUSIVE_ARGS"`、`exit_code == 64`、stderr 为空。
> - 新增 `test_quiet_alone_does_not_trigger_mutex_at_top_level` 显式覆盖"`--quiet` 单独不触发 mutex"。

**实现**(`src/zotero_cli/cli.py`):

```python
"""Top-level Typer app per design §6.

Composes phase 2-5 subapps + schema. Global flags land in ctx.obj as a
GlobalOptions instance; subcommands read attribute style (options.profile).

`GlobalOptions` is defined in Phase 2 (`commands/_runner.py`) so all command
modules can import it without depending on cli.py (avoiding cycles).
"""
from __future__ import annotations

import typer

from zotero_cli.commands import collections, config, feeds, items, schema, tags
from zotero_cli.commands._runner import GlobalOptions  # 阶段 2 已就位


app = typer.Typer(
    name="zotero-cli",
    help="Single-user, agent-first Zotero CLI.",
    no_args_is_help=True,
)
app.add_typer(items.app, name="items")
app.add_typer(collections.app, name="collections")
app.add_typer(tags.app, name="tags")
app.add_typer(feeds.app, name="feeds")
app.add_typer(config.app, name="config")
app.add_typer(schema.app, name="schema")


@app.callback()
def main(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", help="Full JSON envelope output."),
    profile: str = typer.Option("default", "--profile", help="Config profile name."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Print only affected_keys (mutex with --json)."
    ),
) -> None:
    # Mutex 校验由 run_command 在每个命令第一行处理（Phase 2 已就位）。
    # 这里只构造 GlobalOptions 并放进 ctx.obj。
    ctx.obj = GlobalOptions(json_mode=json_mode, profile=profile, quiet=quiet)
```

> **回应 review P1 Issue 2**：`GlobalOptions` 不在本文件重新定义，而是 import 自 `commands/_runner`（阶段 2 Task 6b 创建）。所有 command 模块（包括 schema）都按属性访问 `ctx.obj.profile` / `ctx.obj.json_mode` / `ctx.obj.quiet`，与 phase 3 / 5 保持一致。

> **回应 review P1 Issue 3**：mutex 校验和 stdout/stderr 分离由 `run_command` 统一处理，本 callback 不再做兜底（`run_command` 第一行就拦截 mutex）。

```python
if __name__ == "__main__":  # pragma: no cover
    app()
```

**Steps**:
- [ ] 写测试
- [ ] 跑测试确认失败
- [ ] 写实现
- [ ] 跑测试确认通过
- [ ] `uv run ruff check && uv run mypy src`
- [ ] commit `feat(cli): add top-level Typer app composing all subapps`

---

## Task 2: src/zotero_cli/__main__.py — 入口点

**Files:**
- Modify: `src/zotero_cli/__main__.py`(阶段 1 留的占位)
- Test: `tests/e2e/test_invocation_smoke.py`(新建,极薄)

阶段 1 的 `pyproject.toml` 已经声明 `[project.scripts] zotero-cli = "zotero_cli.__main__:main"`。这里把占位换成真正调用 `cli.app()` 的 `main()`。

**关键测试**(`tests/e2e/test_invocation_smoke.py`):

```python
from __future__ import annotations

import subprocess
import sys


def test_module_invocation_shows_help() -> None:
    """python -m zotero_cli --help must work."""
    result = subprocess.run(
        [sys.executable, "-m", "zotero_cli", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "items" in result.stdout
    assert "schema" in result.stdout


def test_main_function_exists() -> None:
    from zotero_cli.__main__ import main
    assert callable(main)
```

**实现**(`src/zotero_cli/__main__.py`):

```python
"""Console script entry point.

Invoked via `zotero-cli` (pyproject.toml scripts) or `python -m zotero_cli`.
"""
from __future__ import annotations

from zotero_cli.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

---

## Task 3: src/zotero_cli/commands/schema.py — JSON Schema 自省(无 filter)

**Files:**
- Create: `src/zotero_cli/commands/schema.py`
- Test: `tests/unit/test_schema_command.py`

设计 §6 / §7.2:`schema [--command <name>]`,默认输出格式固定为 `json`(忽略 kv/kv-list 路由)。本 Task 实现"全树输出",Task 4 加 `--command` 过滤。

**输出 schema**(envelope 顶层照旧;`data` 形如):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "zotero-cli command tree",
  "version": "0.1.0",
  "commands": {
    "items": {
      "help": "...",
      "subcommands": {
        "list": {"help": "...", "params": [
          {"name": "--limit", "type": "integer", "required": false,
           "default": null, "help": "..."}
        ]}
      }
    }
  }
}
```

设计 §7.2 schema 行约定该命令"默认即 JSON 固定":不论是否传 `--json` 都输出 envelope JSON;`--quiet` 在该命令上**不支持**,报 `MUTUALLY_EXCLUSIVE_ARGS`(退出码 64)。**因为 schema 永远走 json envelope，错误也输出到 stdout**（与设计 §7.5 一致：json 模式下 stdout 永远是合法 JSON envelope）。

**关键测试**:

```python
from __future__ import annotations
import json
from typer.testing import CliRunner

from zotero_cli.cli import app

runner = CliRunner(mix_stderr=False)


def _run(*args: str) -> dict:
    result = runner.invoke(app, ["schema", *args])
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout)


def test_envelope_shape() -> None:
    env = _run()
    assert env["ok"] is True and env["error"] is None
    assert env["meta"]["command"] == "schema"


def test_top_level_includes_all_subapps() -> None:
    data = _run()["data"]
    assert data["title"] == "zotero-cli command tree"
    for sub in ("items", "collections", "tags", "feeds", "config", "schema"):
        assert sub in data["commands"]


def test_subcommand_params_extracted() -> None:
    items_list = _run()["data"]["commands"]["items"]["subcommands"]["list"]
    names = {p["name"] for p in items_list["params"]}
    # design §6: items list at minimum exposes these
    assert {"--limit", "--collection", "--tag", "--all-fields"} <= names


def test_quiet_rejected_on_schema_writes_envelope_to_stdout() -> None:
    """schema 强制 json envelope 输出，--quiet 也走 stdout（envelope ok=false），stderr 空。"""
    result = runner.invoke(app, ["--quiet", "schema"])
    assert result.exit_code == 64
    assert result.stderr == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"
    assert parsed["meta"]["command"] == "schema"
    assert parsed["meta"]["exit_code"] == 64
```

**实现**(`src/zotero_cli/commands/schema.py`):

```python
"""schema command: introspect command tree (design §6 / §7.2).

The schema command is special: it always emits envelope JSON to stdout
(json_mode=True forced), even on errors (per design §7.2 schema row +
§7.5 json-mode invariant). All paths go through run_command.
"""
from __future__ import annotations

from typing import Any

import click
import typer

from zotero_cli import __version__
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.utils.output import OutputMode

app = typer.Typer(name="schema", help="Introspect CLI command tree as JSON Schema.")


def _param(p: click.Parameter) -> dict[str, Any]:
    type_name = getattr(p.type, "name", None) or p.type.__class__.__name__.lower()
    return {
        "name": p.opts[0] if p.opts else (p.name or ""),
        "type": type_name,
        "required": bool(p.required),
        "default": p.default if p.default is not Ellipsis else None,
        "help": getattr(p, "help", None),
    }


def _node(cmd: click.Command) -> dict[str, Any]:
    node: dict[str, Any] = {
        "help": cmd.help or "",
        "params": [_param(p) for p in cmd.params if isinstance(p, click.Option)],
    }
    if isinstance(cmd, click.Group):
        ctx = click.Context(cmd)
        node["subcommands"] = {
            name: _node(sub)
            for name in cmd.list_commands(ctx)
            if (sub := cmd.get_command(ctx, name)) is not None
        }
    return node


def _root() -> click.Group:
    from zotero_cli.cli import app as root_app  # lazy: avoid cli<->schema cycle

    cmd = typer.main.get_command(root_app)
    assert isinstance(cmd, click.Group)
    return cmd


def _full_schema() -> dict[str, Any]:
    root = _root()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "zotero-cli command tree",
        "version": __version__,
        "commands": _node(root)["subcommands"],
    }


@app.callback(invoke_without_command=True)
def schema_cmd(
    ctx: typer.Context,
    command: str | None = typer.Option(
        None, "--command",
        help="Filter to a specific command path (e.g. items.list).",
    ),
) -> None:
    """schema 命令永远输出 JSON envelope（设计 §7.2 schema 行）。

    - 不论用户是否传 `--json`，都强制 json_mode=True；
    - `--quiet` 在 schema 上不支持 → run_command 第 2 步（mode=JSON + quiet 校验）拦截；
    - `--command items.foo` 找不到 → work() 抛 UsageError → runner 渲染失败 envelope。
    """
    options: GlobalOptions = ctx.obj if ctx.obj is not None else GlobalOptions()
    forced_options = GlobalOptions(
        profile=options.profile,
        json_mode=True,           # 设计 §7.2 schema 行：永远 json
        quiet=options.quiet,      # 保留原值；run_command 会拦截 quiet+JSON
        config_path=options.config_path,
    )

    def work() -> dict[str, Any]:
        if command is None:
            return _full_schema()
        return _resolve_path(command)  # 抛 UsageError 由 run_command 渲染

    run_command(
        command="schema", mode=OutputMode.JSON,
        options=forced_options, work=work,
    )


def _resolve_path(path: str) -> dict[str, Any]:
    """根据 'items.list' 这种点路径定位 click.Command；找不到抛 UsageError。"""
    from zotero_cli.cli import app as root_app
    from zotero_cli.models.errors import UsageError

    root_cmd = typer.main.get_command(root_app)
    assert isinstance(root_cmd, click.Group)
    current: click.Command = root_cmd
    parts = path.split(".")
    for i, part in enumerate(parts):
        if not isinstance(current, click.Group):
            raise UsageError(
                f"'{'.'.join(parts[:i])}' has no subcommands",
                hint="Run 'zotero-cli schema' to see the full tree.",
            )
        nxt = current.get_command(click.Context(current), part)
        if nxt is None:
            raise UsageError(
                f"unknown command path: '{path}'",
                hint="Run 'zotero-cli schema' to see available commands.",
            )
        current = nxt
    return _node(current)
```

> **回应 review P1 Issue 2**：schema 的所有路径——成功 / `--quiet` 拒绝 / `--command` 不存在——**全部经过 `run_command`**。
>
> - `--quiet` 拦截：发生在 `run_command` 第 2 步（mode-specific quiet 校验，Phase 2 Task 6b 已实现），`work()` 不会被调；envelope failure 走 stdout（json_mode=True 强制）。
> - `--command items.foo` 失败：`_resolve_path` 抛 `UsageError`，`run_command` 第 3 步捕获，envelope failure 走 stdout。
> - 成功：`work()` 返回 dict，`run_command` 第 4 步渲染 JSON envelope 到 stdout。
>
> 本模块**完全不调** `typer.echo(err=True)` / `typer.Exit` / 手工 `Envelope.success`。`models/errors.py` 的 `UsageError` 由 Phase 1 Task 4 已定义（code=`USAGE_ERROR`，exit_code=64）。

**Steps**: 写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(schema): emit full command tree via run_command (handles --command path + --quiet uniformly)`

---

## Task 4: schema --command NAME 过滤 — 补强测试

**Files:** Modify `tests/unit/test_schema_command.py`

`--command` 选项与 `_resolve_path` 已在 Task 3 一并实现（统一走 `run_command`）。本任务只补 path-filter 的端到端覆盖，验证：

- 顶级过滤 / 嵌套过滤 / 未知顶级 / 未知嵌套 / 中段非 group 的失败信号
- 失败路径**全部经过 envelope JSON**（schema json_mode=True 强制）
- 不出现 `typer.echo(err=True)` / `typer.Exit(64)` 直接路径

**关键测试**:

```python
def test_filter_top_level() -> None:
    result = runner.invoke(app, ["schema", "--command", "items"])
    assert result.exit_code == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)["data"]
    assert "subcommands" in data
    assert "list" in data["subcommands"]


def test_filter_nested() -> None:
    result = runner.invoke(app, ["schema", "--command", "items.list"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    names = {p["name"] for p in data["params"]}
    assert "--limit" in names
    assert "subcommands" not in data


def test_filter_unknown_top_level_writes_envelope_to_stdout() -> None:
    """schema 强制 json envelope 输出。"""
    result = runner.invoke(app, ["schema", "--command", "nonexistent"])
    assert result.exit_code == 64
    assert result.stderr == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "USAGE_ERROR"
    assert "nonexistent" in parsed["error"]["message"]


def test_filter_unknown_nested_writes_envelope() -> None:
    result = runner.invoke(app, ["schema", "--command", "items.nope"])
    assert result.exit_code == 64
    assert result.stderr == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "USAGE_ERROR"


def test_filter_middle_not_group_writes_envelope() -> None:
    """items.list 是 leaf，不能再下钻 'items.list.foo'。"""
    result = runner.invoke(app, ["schema", "--command", "items.list.foo"])
    assert result.exit_code == 64
    parsed = json.loads(result.stdout)
    assert "has no subcommands" in parsed["error"]["message"]
```

> **回应 review P1 Issue 2**：本任务不再有"另一份" `schema_cmd` 实现。失败路径与成功路径走同一个 `run_command`，由 Task 3 一次性实现 + 测试。

**Steps**:
- [ ] 写本任务的补强测试（5 个 case）
- [ ] 跑测试确认全过（实现已在 Task 3 完成）
- [ ] commit `test(schema): cover --command path filter edge cases (envelope-only output)`

---

## Task 5: README.md — 完整文档替换占位

**Files:** Modify `README.md`(阶段 1 占位)

**约束**:用户面向、英文、不写无用 badge。包含:Install / Quickstart(`config init` + 第一次 `items list`) / 两个 agent 调用例子(一个 `--quiet`、一个 `--json`)/ Links(设计文档、DEVELOPMENT.md、`schema` 命令)。

**完整内容**:

````markdown
# zotero-cli

Single-user, agent-first command-line interface for Zotero. Covers literature
management, PDF upload (Zotero File Storage by default; WebDAV when configured),
and read-only RSS feed queries against the local `zotero.sqlite`.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> zotero-cli
cd zotero-cli
uv sync
```

The console script `zotero-cli` is installed into the project's virtualenv;
invoke via `uv run zotero-cli ...` or activate the venv first.

## Quickstart

1. Create a config profile (writes `~/.config/zotero-cli/config.toml`,
   permissions `0600`):

   ```bash
   uv run zotero-cli config init
   ```

   Edit the file to set `api_key` and `library_id` (get from
   <https://www.zotero.org/settings/keys>). `library_type` is `user` for
   personal libraries or `group` for group libraries.

2. List the first 10 items:

   ```bash
   uv run zotero-cli items list --limit 10
   ```

## Agent invocations

Pipe affected item keys into another command (writes only — `--quiet` emits one
key per line, nothing on no-op or failure; see design §7.2.1):

```bash
uv run zotero-cli --quiet items create \
    --type journalArticle --title "Attention is All You Need" \
    --attach paper.pdf | xargs -r -I{} echo "created {}"
```

Get the full JSON envelope for scripting with `jq`:

```bash
uv run zotero-cli --json items list --limit 5 \
  | jq '.data[] | {key, title}'
```

## Introspecting the CLI

For agents that prefer machine-readable command definitions over parsing
`--help`, use the `schema` command:

```bash
# Full command tree
uv run zotero-cli schema

# Single subcommand
uv run zotero-cli schema --command items.list
```

Output is always a JSON envelope (`data` is a JSON-Schema-flavored object).

## Links

- [Design spec](docs/superpowers/specs/2026-06-07-zotero-cli-design.md) -
  full feature surface, output formats, error codes, WebDAV protocol.
- [DEVELOPMENT.md](DEVELOPMENT.md) - contributor / agent collaboration rules.
- [Zotero Web API v3](https://www.zotero.org/support/dev/web_api/v3/) -
  upstream API reference.

## License

TBD.
````

## Task 6: 设计 §12.5 手动测试清单执行

**Files:** 不新建文件;结果写入 PR 描述的"手动测试结果"段落。

按设计 §12.5 表格逐项实测,**每项必须勾选**。前置:Task 1-5 已合并,且本机有可用的 personal Zotero 账号 + 一个仅供测试的 group library + 一个 WebDAV server(可用本地 wsgidav 起一个,或用真实 Box/Nextcloud)。

**逐项 sub-step**(全部勾选才算 Task 完成):

- [ ] **6.1 ZFS 后端默认上传**:profile 不配 `[webdav]`,`uv run zotero-cli items create --type journalArticle --title "ZFS Test" --attach tests/fixtures/sample_pdf.pdf`,记录 attachment_key,在 Zotero 桌面端能打开 PDF
- [ ] **6.2 WebDAV 后端上传**:profile 加 `[webdav]` 段,同样命令,Zotero 桌面端能识别并打开
- [ ] **6.3 后端切换**:删 `[webdav]` 后再上传一次,envelope `data.backend == "zfs"` 且 `meta.backend == "zfs"`;加回再上传,值变成 `"webdav"`
- [ ] **6.4 group library 拒绝 WebDAV**:把 profile 改 `library_type = "group"` 并保留 `[webdav]`,跑 `config validate`,退出码 1,错误码 `UNSUPPORTED_LIBRARY_TYPE`
- [ ] **6.5 `--attach-title` 不污染父 item title**(ZFS):`items create --type journalArticle --title "Paper X" --attach paper.pdf --attach-title "Main PDF"`,然后 `items show <parent>` 验证 title="Paper X",attachment 验证 title="Main PDF"。再省略 `--attach-title` 验证 attachment title=文件名
- [ ] **6.6 `--attach-title` 不污染父 item title**(WebDAV):同 6.5,profile 切到带 `[webdav]` 的
- [ ] **6.7 `items attach --title` 是附件 title**:`items attach <parent> file.pdf --title "Custom Att"`,验证 attachment.title="Custom Att"
- [ ] **6.8 `--reuse-key` ZFS 路径**:第一次 attach 拿到 att-key → 改本地 PDF 内容 → `items attach <parent> file.pdf --reuse-key <att-key>` → 远端 md5 已更新、key 不变
- [ ] **6.9 `--reuse-key` WebDAV 路径**:第一次 attach → 手动删远端 prop → `items attach <parent> file.pdf --reuse-key <att-key>` → 远端 zip+prop 都恢复
- [ ] **6.10 `--reuse-key` 不存在的 key**:`items attach <parent> file.pdf --reuse-key NONEXIST` 退出码 1,错误码 `ITEM_NOT_FOUND`
- [ ] **6.11 ZFS 后端 `--force` 被拒**:`items attach <parent> file.pdf --reuse-key <att-key> --force`(profile 无 `[webdav]`)→ 退出码 64,错误码 `MUTUALLY_EXCLUSIVE_ARGS`,stderr 含设计 §10.0.2.3 提示文案
- [ ] **6.12 WebDAV `--force` 跳过 md5 检测**:第一次 `--reuse-key` 命中 unchanged(`data.uploaded=[]`、`data.unchanged=[…]`);加 `--force` 后走 uploaded(remote prop mtime 更新)
- [ ] **6.13 `--quiet` 不输出 unchanged/failed**:WebDAV `--reuse-key` 命中 unchanged → `--quiet` 输出空(0 字节、退出码 0);加 `--force` → `--quiet` 输出一行 attachment key
- [ ] **6.14 mtime 一致性**(WebDAV):上传后 Zotero 桌面端不触发"重新上传"
- [ ] **6.15 base64 编码方式**(WebDAV):桌面端上传 PDF,下载 zip 检查内部文件名,与 CLI 上传的 zip 比对一致
- [ ] **6.16 多平台 sqlite 路径检测**:Linux 一台机器上跑 `config validate` 自动检测到本机 `~/Zotero/zotero.sqlite`;若没有真实路径则用 `ZOTERO_DATA_DIR` 环境变量临时指向 fixture 验证检测优先级
- [ ] **6.17 大文件上传(100MB)**:用 `dd if=/dev/urandom bs=1M count=100 of=large.pdf` 造样本,`items attach` 不 OOM、有进度提示

每项填一行结果(命令 + 实测输出关键行 + pass/fail)粘到 PR 描述。任意一项 fail 不进合并,先开 issue 修。

**Steps**:
- [ ] 准备测试账号 / WebDAV server
- [ ] 跑完 17 项
- [ ] 把结果汇总贴 PR 描述
- [ ] commit `chore: tick design §12.5 manual test results`(只动 DEVELOPMENT.md 勾选;结果不入库)

---

## Task 7: 全项目覆盖率验证(设计 §12.4)

**Files:** 无代码改动(仅补测试 + 跑命令);若有未达标的模块需在该模块的测试文件里补 case。

```bash
uv run pytest --cov=src/zotero_cli --cov-report=term-missing --cov-branch
```

按下表逐行核对:

| 模块 | 目标 | 实测 |
|---|---|---|
| `utils/date_parser.py` | 100% | ____ |
| `adapters/webdav_client.py` | 95%+ | ____ |
| `adapters/sqlite_reader.py` | 90%+ | ____ |
| `services/*` | 85%+ | ____ |
| `commands/*` | 70%+ | ____ |
| `utils/output.py` | 90%+ | ____ |
| **总体** | **85%+** | ____ |

未达标处理:
- 看 `--cov-report=term-missing` 输出的未覆盖行号
- 优先补"业务分支"测试(error path、boundary case),不为覆盖率而写空 assert
- 单测真的够不到的(如顶层 `if __name__ == "__main__"`)用 `# pragma: no cover` 标注并在 PR 描述里列清楚每一处理由

**Steps**:
- [ ] 跑 `pytest --cov`
- [ ] 把每行实测填表
- [ ] 未达标处补测试(每条补一个 commit `test(<module>): cover <case>`)
- [ ] 重跑确认全达标
- [ ] 把最终覆盖率表贴 PR 描述

---

## Task 8: 全项目 mypy strict + ruff 终检

**Files:** 修任何被这两条命令打出问题的源码/测试文件。

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

要求:
- ruff: 0 errors / 0 format diffs(`format --check` 退出码 0)
- mypy strict 全 src: 0 errors

修复纪律:
- mypy 报 `Any` 隐式回退 → 显式标注 `Any` 或换具体类型,**禁止** `# type: ignore` 兜底
- ruff format 有 diff → 直接 `uv run ruff format src tests`
- 第三方库无 stubs 报错 → 看 pyproject.toml `[[tool.mypy.overrides]]` 是否已加该模块;没加就加;**禁止全局 `ignore_errors`**

**Steps**:
- [ ] 跑三条命令
- [ ] 修复任何输出
- [ ] commit(每个独立修复一个 commit,例 `fix(cli): annotate ctx.obj as GlobalOptions`)
- [ ] 把"all green"输出贴 PR 描述

---

## Task 9: DEVELOPMENT.md 修订记录(仅在发现设计偏离时改)

**Files:** Modify `DEVELOPMENT.md` §12 修订记录(可能需要一并修 §9.6 勾选)

按 DEVELOPMENT.md §7.6:阶段 1-5 实施过程中如发现与设计文档偏离的地方,Task 9 是"集中入帐"时机。

**操作**:
- [ ] 翻阅阶段 1-5 已合并 PR 描述里的 "设计偏离 / 提议" 段落
- [ ] 把每一项凝练成一行加到 DEVELOPMENT.md §12 修订记录表

  | 日期 | 改动 | 触发原因 |
  |---|---|---|
  | 2026-06-07 | 初稿 | 设计文档定稿、进入实施前确立协作规范 |
  | YYYY-MM-DD | 阶段 X 实施中 <发现 Y> | <PR #N 链接> |

- [ ] 若发现的偏离影响设计文档本身(不仅是 DEVELOPMENT.md),同步开一个 `docs: align design spec with phase X findings` PR 改设计文档,本 plan 不直接动设计文档
- [ ] 若没有偏离,本 Task 写一句 "无偏离" 在 PR 描述并跳过(不提交空 commit)

**Steps**:
- [ ] 收集偏离
- [ ] 改 DEVELOPMENT.md §12
- [ ] commit `docs: log phase 1-5 design deviations in DEVELOPMENT.md §12`(若有)

---

## Task 10: 阶段 6 验收 checklist 勾选 + 最终 commit

**Files:** Modify `DEVELOPMENT.md` §9.6

把 §9.6 八条 checklist 全部从 `[ ]` 改成 `[x]`(对应 Task 1-9 已交付的内容):

```markdown
### §9.6 阶段 6:Agent 自省 + 收尾

- [x] `commands/schema.py`:命令树 JSON Schema 自省,`--command <name>` 输出指定子命令 schema
- [x] `README.md`:安装、快速开始、典型 agent 调用例子
- [x] 设计 §12.5 手动测试清单全部跑过、记录结果
- [x] 全模块覆盖率达到设计 §12.4 目标
- [x] 审计日志格式与设计 §9.4 一致,10MB 轮转生效
- [x] mypy strict 全项目无 error
- [x] ruff 全项目 clean
- [x] DEVELOPMENT.md 与设计文档已根据实施过程发现的偏离同步更新
```

注意:第 5 项("审计日志格式与设计 §9.4 一致,10MB 轮转生效")在阶段 1 Task 11-13 已实现;此处只是回看复测一次:
- [ ] 跑 `uv run pytest tests/unit/test_audit_log.py -v`,所有 case 绿
- [ ] 临时构造 ≥10MB 的 `audit.log` 后调用 `write_entry` 一次,确认 `audit.log.YYYY-MM.gz` 生成、原文件被截断

**Steps**:
- [ ] 复测审计日志轮转
- [ ] 勾 §9.6 全部
- [ ] commit `docs: tick phase 6 acceptance checklist`
- [ ] 在 PR 描述中粘贴 §9.6 已全勾的快照

---

## Task 11(可选):打 release tag v0.1.0

**Files:** 无源码改动。

只在用户明确要求"出第一个版本"时执行。要求 Task 1-10 全部合并到 `main`、CI/自检全绿。

**Steps**:
- [ ] 确认 `pyproject.toml` 中 `version = "0.1.0"`(阶段 1 已设置,这里只是复核)
- [ ] `git tag -a v0.1.0 -m "zotero-cli 0.1.0: initial release"`
- [ ] `git push origin v0.1.0`(如有 remote;无 remote 则止步在本地 tag)
- [ ] 把 tag 链接贴 PR 描述

不主动发 PyPI(本项目是单用户工具,设计 §1 / §14 没要求公开发布)。

---

## 自检清单(全阶段汇总)

每次 commit 之前(DEVELOPMENT.md §6.6):

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src/zotero_cli --cov-report=term-missing
```

四项全过才能 commit。最后一次自检的输出贴进 Task 10 的 PR 描述。

---

## 阶段 6 最终验收闸(DEVELOPMENT.md §9.6)

合并到 `main` 之前 reviewer 按下表逐条核:

| 闸 | 来源 | 通过条件 |
|---|---|---|
| 命令树自省 | §9.6 第 1 条 | `schema` / `schema --command items.list` 都返回合法 envelope JSON |
| README 完备 | §9.6 第 2 条 | install / quickstart / agent 例子 / 链接齐 |
| 手动测试 17 项全过 | §9.6 第 3 条 + 设计 §12.5 | PR 描述中 17 项全 pass |
| 覆盖率达标 | §9.6 第 4 条 + 设计 §12.4 | 表格每行实测 ≥ 目标;总体 ≥ 85% |
| 审计日志 10MB 轮转 | §9.6 第 5 条 | 现场复测看到 `.gz` 归档生成 |
| mypy strict 全绿 | §9.6 第 6 条 | `mypy src` 0 errors |
| ruff 全绿 | §9.6 第 7 条 | `ruff check` + `ruff format --check` 都 0 |
| 设计偏离已入帐 | §9.6 第 8 条 + DEVELOPMENT.md §7.6 | DEVELOPMENT.md §12 已添加偏离条目,或明确写"无偏离" |

任意一闸未过 → 阶段 6 不算完成 → 不能合并 → 不打 v0.1.0 tag。

阶段 6 完成 = zotero-cli 0.1.0 实施收官。







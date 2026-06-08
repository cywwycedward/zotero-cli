# 阶段 4：附件上传 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**:实现 ZFS（默认）与 WebDAV（可选）两条附件上传路径，覆盖 `items create --attach` / `items update --attach` / `items attach`(含 `--reuse-key` 场景 B 与 `--force`),实现 `_select_backend()` 派发、§10.0.1 兼容性前置校验、§10.0.2.5 ZFS 失败处理与 §10.3 WebDAV 6 步流程的失败回滚,统一 envelope schema(`data.backend` + `uploaded[]` / `unchanged[]` / `failed[]`)与 `meta.affected_keys`。

**Architecture**:两条独立后端路径,由 `services/attachment_service.AttachmentService._select_backend()` 派发。ZFS 路径委托 pyzotero(封装在 `adapters/zotero_api.py` 的扩展层),WebDAV 路径走自实现 `adapters/webdav_client.py`(zip + prop XML + PROPFIND/MKCOL/PUT/DELETE/GET)。失败回滚两路径不同(ZFS 前向修复保留状态供后续修复,WebDAV 反向清理已上传文件)。多文件(≥2)启用 `ThreadPoolExecutor(max_workers=DEFAULT_PARALLEL_UPLOADS)` 并发,单文件走串行。

**Tech Stack**:webdav4 / pyzotero / respx(优先) / pytest-mock / pytest-httpserver(fallback) / `concurrent.futures.ThreadPoolExecutor`。协议字节级 fixture 来自 Task 1 的 spike 实测。

**Source-of-truth references**:
- 设计 §8.3(envelope schema)/ §8.3.1(affected_keys)/ §10(后端、上传流程、回滚、`--force`/`--reuse-key`、并发)/ §13 阶段 4
- DEVELOPMENT.md §6 TDD / §9.4 阶段 4 验收 checklist
- 阶段 1/2/3 已就位:`models.errors`(WebdavFileExistsError / Md5MismatchError / WebdavTimeoutError / WebdavConnectionError / WebdavAuthFailedError / StorageQuotaExceededError / MutuallyExclusiveArgsError / FileNotFoundCLIError / UnsupportedLibraryTypeError 等)、`models.envelope.Envelope.success/failure`、`models.config.WebDAVConfig`、`utils.output.render` + `OutputMode.SUMMARY`、`utils.audit_log.AuditEntry/write_entry`、`constants.DEFAULT_PARALLEL_UPLOADS`、`adapters.zotero_api.ZoteroAPI`、`services.item_service.ItemService`、`services.config_service.load_config`
- 阶段 4 前置 spike:`docs/superpowers/specs/spikes/webdav-protocol.md`(Task 1 产出)

**关键判断(实施前确认,贯穿后续任务)**:
- WebDAV 后端的 `--force` 跳过 §10.5 场景 B 的远端 md5 检测;**仅 `items attach --reuse-key` 命令(场景 B)接受 `--force`**。场景 A(`items create --attach`、`items update --attach`、不带 `--reuse-key` 的 `items attach`)**永不接受 `--force`**——根据 §10.5 表格"是否触发已存在检测=否",每次新建 attachment 都会拿到全新 key,远端必然不存在,`--force` 无意义。
- ZFS 后端**任何场景**下 `--force` 都被拒绝,直接抛 `MutuallyExclusiveArgsError`(§10.0.2.3)。
- WebDAV 路径仅在**单次命令上传 ≥2 个文件**时启用 `ThreadPoolExecutor`,单文件走串行(避免线程开销与 mock 复杂度)。
- 群组 library + WebDAV 在 `services.attachment_service.attach()` 入口先于任何 I/O **再校验一次**(防御 config 绕过),不通过抛 `UnsupportedLibraryTypeError`。

---

## 文件结构

```
zotero-cli/
├── docs/superpowers/specs/spikes/
│   └── webdav-protocol.md                    # NEW(Task 1)
├── src/zotero_cli/
│   ├── adapters/
│   │   ├── zotero_api.py                     # EXTEND(attachment_simple/both/upload_attachments/Zupload 包装 + 异常翻译扩展)
│   │   └── webdav_client.py                  # NEW(WebDAVClient + build_zip + build_prop / parse_prop + 路径拼接 + 错误翻译)
│   ├── services/
│   │   └── attachment_service.py             # NEW(_select_backend + 前置校验 + ZFS/WebDAV 双路径 + 回滚 + 并发 + 审计)
│   ├── commands/
│   │   └── items.py                          # EXTEND(--attach 选项 on create/update、attach 子命令、--reuse-key、--force)
│   └── models/
│       └── attachment.py                     # NEW(AttachmentResult / PropMetadata pydantic 模型,统一 schema)
└── tests/
    ├── fixtures/
    │   ├── sample_pdf.pdf                    # 阶段 1 已占位;若空则补 5KB 真 PDF
    │   ├── sample_prop.xml                   # NEW(spike 抓取,字节级 fixture)
    │   └── sample_zip_internal.txt           # NEW(spike 记录 zip 内部文件名编码)
    ├── unit/
    │   ├── test_webdav_client.py             # NEW(PROPFIND/PUT/zip/prop XML/路径/错误翻译)
    │   ├── test_zotero_api_attach.py         # NEW(attachment_simple/both/upload_attachments/Zupload 包装)
    │   └── test_attachment_service.py        # NEW(派发、前置校验、ZFS/WebDAV、回滚、并发、affected_keys)
    └── integration/
        └── test_attach_e2e.py                # NEW(pytest-httpserver 起本地 WebDAV,跑完整 6 步、模拟 kill 连接验证回滚)
```

## 模块依赖关系

```
spikes/webdav-protocol.md
        ↓
webdav_client.py (核心方法 + zip + prop + 路径 + 错误翻译) ← models.errors / models.config.WebDAVConfig
        ↓
zotero_api.py (extend with 4 attachment APIs) ← models.errors
        ↓
attachment_service.py ← zotero_api / webdav_client / item_service / audit_log / constants / models.attachment
        ↓
commands/items.py (--attach + attach 子命令) ← attachment_service / output / config_service
```

**任务执行顺序**:1(spike) → 2-6(webdav_client 渐进) → 7(zotero_api 扩展) → 8(attachment_service 派发与前置校验) → 9-12(ZFS 路径) → 13-16(WebDAV 路径) → 17(并发) → 18(envelope schema) → 19(affected_keys) → 20(commands) → 21(手动验证) → 22(验收 tick)。

Task 13-16 可与 Task 9-12 在不同 worktree 并行(DEVELOPMENT.md §7.3),但 Task 17 之前必须先合并;Task 18-19 在所有路径就绪后做最终统一验证。

---

## Task 1: WebDAV 协议 spike

**Files:**
- Create: `docs/superpowers/specs/spikes/webdav-protocol.md`
- Create: `tests/fixtures/sample_prop.xml`(从 Zotero 桌面端抓取的真实文件)
- Create: `tests/fixtures/sample_zip_internal.txt`(记录 zip 内部文件名编码)

DEVELOPMENT.md §9.4 要求实测以下四个风险点(设计 §10.6),写入 spike 文档供 Task 2-6 引用为字节级真值。spike 用真实 Zotero 桌面端 + 一台 WebDAV server(自建 nginx-dav 或 Nextcloud,凭据放本地 `.spike-env`,**不入库**)。

- [ ] **Step 1**:用 Zotero 桌面端(配 WebDAV)上传一个 ASCII 文件名 PDF + 一个含中文/空格/`+` 的 PDF,把服务器上的 `.zip` 拖回本地

- [ ] **Step 2**:用 Python `zipfile` 读两个 zip,记录内部 entry 的 `filename` 字段 raw bytes 与 decode 方式
  - 记录到 `sample_zip_internal.txt`:`原始文件名 | 内部存储字节(hex) | 编码方案(b64 / b64url / raw utf-8 / 其他)`
  - 验证压缩级别(应为 `ZIP_STORED`,即 `compress_type=0`)

- [ ] **Step 3**:抓取 `<key>.prop` 的原始字节(`curl -u user:pass https://.../zotero/<key>.prop -o sample_prop.xml`),记录:
  - 是否带 XML declaration(`<?xml ...?>`)、是否有换行、缩进、属性顺序(`version="1"` 在前还是后)
  - `mtime` 是 10 位秒还是 13 位毫秒,精度截断方式
  - `hash` 大小写、有无前后空白
  - 字节级 hexdump 写入 spike 文档

- [ ] **Step 4**:测试 `storage_path` 变体——分别配 `""`(根目录)、`/zotero`、`/dav/zotero/sub` 三种,确认:
  - 根目录是否需要 MKCOL(应跳过)
  - 多级子目录是否需要逐级 MKCOL
  - 桌面端默认 `storage_path` 是什么(可能因服务器而异)

- [ ] **Step 5**:验证 mtime 一致性——上传后立即在 Zotero 桌面端"检查同步",确认不被识别为"远程已修改"。如触发,说明 mtime 截断/精度有问题,回到 Step 3 校准。

- [ ] **Step 6**:验证 respx 是否能拦截 webdav4——本地起一段简单脚本 `import respx; with respx.mock: webdav4.Client(...).propfind(...)` ,看 respx 路由是否命中。命中→后续 unit test 用 respx;不命中→标记 fallback 到 pytest-httpserver(`uv sync --extra webdav-test`)。

- [ ] **Step 7**:把全部发现写入 `webdav-protocol.md`,模板:
  ```
  # WebDAV Protocol Spike(2026-06-07)
  ## 1. zip 内部文件名编码
  - 编码方案:_____(标准 b64 / b64url / 其他)
  - 验证样本:见 tests/fixtures/sample_zip_internal.txt
  - Python 实现:`base64.b64encode(name.encode("utf-8")).decode("ascii")`(或对应方案)
  ## 2. ZIP 压缩
  - compress_type = ZIP_STORED(0)
  ## 3. .prop 字节级格式
  - hexdump:_____
  - 模板字符串(Python f-string):_____(直接复制可用)
  - mtime 精度:13 位毫秒
  ## 4. storage_path 变体
  - 默认:_____;空字符串行为:_____;多级 MKCOL:_____
  ## 5. mtime 一致性结论
  - 桌面端不触发重传:✅/❌
  ## 6. respx vs pytest-httpserver
  - 拦截 webdav4 结果:_____
  - 后续 mock 策略:_____
  ```

- [ ] **Step 8**:commit
  ```bash
  git add docs/superpowers/specs/spikes/webdav-protocol.md tests/fixtures/sample_prop.xml tests/fixtures/sample_zip_internal.txt
  git commit -m "docs(spike): record WebDAV protocol byte-level findings per design §10.6"
  ```

**与设计冲突时**:回头修订 §10.1 / §10.2 再继续 Task 2(DEVELOPMENT.md §7.6)。

---

## Task 2: webdav_client.py — WebDAVClient 核心方法

**Files:**
- Create: `src/zotero_cli/adapters/webdav_client.py`
- Test: `tests/unit/test_webdav_client.py`

封装 webdav4.Client,实现 `propfind / mkcol / put / delete / get / exists` 六个方法。本任务只做核心 HTTP 调用(无 zip / prop / 业务逻辑),所有方法接收**已拼好**的绝对路径(基于 `WebDAVConfig.url`)。**不**做异常翻译——留给 Task 6。

- [ ] **Step 1: 写失败测试**

`tests/unit/test_webdav_client.py`(若 spike Step 6 确认 respx 不可用,改用 pytest-httpserver,逻辑等价):

```python
from __future__ import annotations
import pytest
import respx
from httpx import Response
from zotero_cli.adapters.webdav_client import WebDAVClient
from zotero_cli.models.config import WebDAVConfig


@pytest.fixture
def cfg() -> WebDAVConfig:
    return WebDAVConfig(url="https://dav.example.com", storage_path="/zotero",
                        username="u", password="p", timeout=10, verify_ssl=True)


class TestPropfind:
    @respx.mock
    def test_returns_true_for_207(self, cfg: WebDAVConfig) -> None:
        respx.request("PROPFIND", "https://dav.example.com/zotero/").mock(
            return_value=Response(207, text="<multistatus/>")
        )
        client = WebDAVClient(cfg)
        assert client.exists("/zotero/") is True

    @respx.mock
    def test_returns_false_for_404(self, cfg: WebDAVConfig) -> None:
        respx.request("PROPFIND", "https://dav.example.com/zotero/").mock(
            return_value=Response(404)
        )
        assert WebDAVClient(cfg).exists("/zotero/") is False


class TestPut:
    @respx.mock
    def test_uploads_bytes(self, cfg: WebDAVConfig) -> None:
        route = respx.put("https://dav.example.com/zotero/X.zip").mock(
            return_value=Response(201)
        )
        WebDAVClient(cfg).put("/zotero/X.zip", b"PK\x03\x04...", content_type="application/zip")
        assert route.called
        assert route.calls[0].request.content == b"PK\x03\x04..."


class TestDelete:
    @respx.mock
    def test_404_treated_as_success(self, cfg: WebDAVConfig) -> None:
        respx.delete("https://dav.example.com/zotero/X.prop").mock(
            return_value=Response(404)
        )
        WebDAVClient(cfg).delete("/zotero/X.prop")  # 不抛
```

- [ ] **Step 2: 实现框架**(只到能让上述测试通过)

`src/zotero_cli/adapters/webdav_client.py`:
```python
"""WebDAV client wrapping webdav4 with project-specific path joining and exception
translation. Per design §10.0.3 / §10.2."""
from __future__ import annotations
from webdav4.client import Client as _Webdav4Client
from zotero_cli.models.config import WebDAVConfig


class WebDAVClient:
    def __init__(self, cfg: WebDAVConfig) -> None:
        self._cfg = cfg
        self._client = _Webdav4Client(
            base_url=cfg.url, auth=(cfg.username, cfg.password),
            timeout=cfg.timeout, verify=cfg.verify_ssl,
        )

    def exists(self, path: str) -> bool:
        # 用 PROPFIND depth=0,404→False,207→True
        ...

    def propfind(self, path: str) -> bytes: ...
    def mkcol(self, path: str) -> None: ...
    def put(self, path: str, data: bytes, *, content_type: str) -> None: ...
    def delete(self, path: str) -> None: ...  # 404 视为成功
    def get(self, path: str) -> bytes: ...
```

- [ ] **Step 3**:跑测试 + commit

```bash
uv run pytest tests/unit/test_webdav_client.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/adapters/webdav_client.py tests/unit/test_webdav_client.py
git commit -m "feat(webdav_client): add core PROPFIND/MKCOL/PUT/DELETE/GET wrappers"
```

---

## Task 3: webdav_client.py — build_zip(base64 文件名 + ZIP_STORED)

**Files:**
- Modify: `src/zotero_cli/adapters/webdav_client.py`
- Modify: `tests/unit/test_webdav_client.py`

按 spike Task 1 Step 2 的发现实现 zip 构造。Zotero 协议要求内部文件名 base64 编码、不压缩(`ZIP_STORED`)。

- [ ] **Step 1**:写失败测试(常量来自 spike fixture)

```python
import zipfile, io, base64
from pathlib import Path
from zotero_cli.adapters.webdav_client import build_zip

def test_build_zip_uses_base64_filename(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n...EOF")
    zip_bytes = build_zip(pdf, key="ABC123XY")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        assert len(names) == 1
        # spike 确认编码方案,这里以标准 b64 为例;若 spike 发现 b64url,调整 expected
        expected = base64.b64encode(b"paper.pdf").decode("ascii")
        assert names[0] == expected
        info = z.getinfo(names[0])
        assert info.compress_type == zipfile.ZIP_STORED
        with z.open(names[0]) as f:
            assert f.read() == b"%PDF-1.4\n...EOF"

def test_build_zip_unicode_filename(tmp_path: Path) -> None:
    pdf = tmp_path / "论文 v2.pdf"
    pdf.write_bytes(b"%PDF")
    zip_bytes = build_zip(pdf, key="K")
    # 仅验证能解码、不崩;具体值依 spike
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        decoded = base64.b64decode(z.namelist()[0])
        assert decoded == "论文 v2.pdf".encode("utf-8")
```

- [ ] **Step 2: 实现**(具体 base64 变体由 spike 决定;以下是标准 b64 默认)

```python
import base64
import zipfile
import io
from pathlib import Path

def build_zip(file_path: Path, *, key: str) -> bytes:
    """构造 Zotero WebDAV 用的 zip。内部文件名 base64,内容 ZIP_STORED。
    见设计 §10.1 / spikes/webdav-protocol.md §1-§2。"""
    encoded_name = base64.b64encode(file_path.name.encode("utf-8")).decode("ascii")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr(encoded_name, file_path.read_bytes())
    return buf.getvalue()
```

- [ ] **Step 3**:测 + commit `feat(webdav_client): add build_zip with base64 filename and ZIP_STORED`

---

## Task 4: webdav_client.py — build_prop / parse_prop XML 字节级一致

**Files:** Modify webdav_client.py 和 test_webdav_client.py

按 spike Step 3 抓取的 `sample_prop.xml` fixture 做字节级 round-trip。**不用 lxml/ET 之类的格式化输出**——用 f-string 直接生成,保证字节匹配 spike 抓的真实样本(空格、换行、属性顺序)。

- [ ] **Step 1: 测试**

```python
from pathlib import Path
from zotero_cli.adapters.webdav_client import build_prop, parse_prop, PropMetadata

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_prop.xml"

def test_build_prop_byte_exact_match_spike_sample() -> None:
    # spike 抓的样本里假设的值(实际从 sample_prop.xml 读出代入)
    # 例:mtime=1717584321000, hash=d41d8cd98f00b204e9800998ecf8427e
    expected = FIXTURE.read_bytes()
    # 从 fixture 反向解析出参数,然后再生成,确保 build/parse 互逆
    meta = parse_prop(expected)
    rebuilt = build_prop(md5=meta.hash, mtime_ms=meta.mtime_ms)
    assert rebuilt == expected, f"byte mismatch:\nexpected={expected!r}\nactual={rebuilt!r}"

def test_parse_prop_extracts_md5_and_mtime() -> None:
    xml = b'<properties version="1"><mtime>1717584321000</mtime>' \
          b'<hash>d41d8cd98f00b204e9800998ecf8427e</hash></properties>'
    meta = parse_prop(xml)
    assert meta.mtime_ms == 1717584321000
    assert meta.hash == "d41d8cd98f00b204e9800998ecf8427e"

def test_round_trip_arbitrary_values() -> None:
    out = build_prop(md5="a" * 32, mtime_ms=1234567890000)
    parsed = parse_prop(out)
    assert parsed.hash == "a" * 32
    assert parsed.mtime_ms == 1234567890000
```

- [ ] **Step 2: 实现**(模板字符串以 spike 抓取的样本为准;以下是常见单行格式)

> **回应 review P2 Issue 3**：`parse_prop` 解析失败必须抛 `WebdavPropInvalidError`（设计 §9.2 已加入；Phase 1 errors.py 已加入），不再裸 `ValueError`。理由：远端 `.prop` 是**外部输入**（任何写到 WebDAV 的工具都可能影响它），按 DEVELOPMENT.md §4.3 需要走 CLIError 体系，让 `run_command` 在 command 层正常渲染失败 envelope（local_error，退出码 4）。

```python
from dataclasses import dataclass
import re

from zotero_cli.models.errors import WebdavPropInvalidError


@dataclass(frozen=True)
class PropMetadata:
    mtime_ms: int
    hash: str

# 模板:严格按 spike 字节级样本写,空格/换行/属性顺序勿改
_PROP_TEMPLATE = '<properties version="1"><mtime>{mtime}</mtime><hash>{md5}</hash></properties>'
_MTIME_RE = re.compile(rb"<mtime>(\d+)</mtime>")
_HASH_RE = re.compile(rb"<hash>([0-9a-f]{32})</hash>")

def build_prop(*, md5: str, mtime_ms: int) -> bytes:
    return _PROP_TEMPLATE.format(mtime=mtime_ms, md5=md5).encode("ascii")

def parse_prop(xml_bytes: bytes, *, source_path: str | None = None) -> PropMetadata:
    """Parse Zotero WebDAV .prop XML.

    Raises:
        WebdavPropInvalidError: when mtime / hash fields are missing,
            malformed, or when bytes are not ascii-decodable. context 字段填
            原始 bytes 前 80 字节（截断防日志爆炸）+ 远端路径（如有）。
    """
    m = _MTIME_RE.search(xml_bytes)
    h = _HASH_RE.search(xml_bytes)
    if not m or not h:
        ctx: dict[str, object] = {"raw_head": xml_bytes[:80].decode("latin-1", errors="replace")}
        if source_path is not None:
            ctx["source_path"] = source_path
        raise WebdavPropInvalidError(
            "Malformed Zotero WebDAV .prop XML (mtime / hash missing or invalid)",
            hint="Re-upload the attachment via Zotero desktop, or run 'items attach --reuse-key <key> --force' to overwrite.",
            context=ctx,
        )
    return PropMetadata(mtime_ms=int(m.group(1)), hash=h.group(1).decode("ascii"))
```

**关键测试**（补强：替换原 `pytest.raises(ValueError)`）:

```python
import pytest
from zotero_cli.adapters.webdav_client import parse_prop
from zotero_cli.models.errors import WebdavPropInvalidError


def test_parse_prop_missing_mtime_raises_webdav_prop_invalid() -> None:
    with pytest.raises(WebdavPropInvalidError) as ei:
        parse_prop(b'<properties version="1"><hash>' + b"a" * 32 + b'</hash></properties>')
    assert ei.value.code == "WEBDAV_PROP_INVALID"
    assert ei.value.exit_code == 4
    assert "raw_head" in ei.value.context


def test_parse_prop_missing_hash_raises() -> None:
    with pytest.raises(WebdavPropInvalidError):
        parse_prop(b'<properties version="1"><mtime>123</mtime></properties>')


def test_parse_prop_garbage_raises_with_source_path_context() -> None:
    with pytest.raises(WebdavPropInvalidError) as ei:
        parse_prop(b"not xml at all", source_path="/zotero/ATT.prop")
    assert ei.value.context["source_path"] == "/zotero/ATT.prop"


def test_parse_prop_invalid_md5_length_raises() -> None:
    """hash 不是 32 个十六进制字符 → 正则不命中 → 抛"""
    with pytest.raises(WebdavPropInvalidError):
        parse_prop(b'<properties version="1"><mtime>1</mtime><hash>tooshort</hash></properties>')
```

**端到端**（场景 B 重传时 `parse_prop` 失败应被 runner 捕获，envelope 带 `WEBDAV_PROP_INVALID`）：

```python
@respx.mock
def test_scenario_b_remote_prop_corrupt_returns_webdav_prop_invalid_envelope(
    runner_obj, mocker, tmp_path
) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    respx.head("https://x/zotero/ATT.prop").mock(return_value=Response(200))
    respx.get("https://x/zotero/ATT.prop").mock(return_value=Response(200, content=b"<corrupt/>"))
    result = cli_runner.invoke(
        items_app,
        ["attach", "P", str(pdf), "--reuse-key", "ATT"],
        obj=make_global_options(profile="webdav-profile", json_mode=True),
    )
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "WEBDAV_PROP_INVALID"
    assert result.exit_code == 4
```

- [ ] **Step 3**:测 + commit `feat(webdav_client): add build_prop/parse_prop with byte-exact XML template`

---

## Task 5: webdav_client.py — storage_path-aware 路径拼接

**Files:** Modify webdav_client.py 和 test_webdav_client.py

`WebDAVConfig.storage_path` 已在阶段 2 normalize(空字符串 / 以 `/` 开头无尾随)。本任务在 client 上加 `path_for_key(key, ext)` 辅助,统一拼接路径,所有 WebDAV 业务调用走这个方法。

- [ ] **Step 1: 测试**

```python
import pytest
from zotero_cli.adapters.webdav_client import WebDAVClient
from zotero_cli.models.config import WebDAVConfig

@pytest.mark.parametrize("storage_path,key,ext,expected", [
    ("/zotero", "ABC", "zip", "/zotero/ABC.zip"),
    ("/zotero", "ABC", "prop", "/zotero/ABC.prop"),
    ("", "ABC", "zip", "/ABC.zip"),
    ("/dav/zotero/sub", "K", "zip", "/dav/zotero/sub/K.zip"),
])
def test_path_for_key(storage_path: str, key: str, ext: str, expected: str) -> None:
    cfg = WebDAVConfig(url="https://x", storage_path=storage_path,
                       username="u", password="p", timeout=10, verify_ssl=True)
    assert WebDAVClient(cfg).path_for_key(key, ext) == expected

def test_path_for_storage_root() -> None:
    cfg = WebDAVConfig(url="https://x", storage_path="/zotero",
                       username="u", password="p", timeout=10, verify_ssl=True)
    # storage 根(用于 PROPFIND/MKCOL) — 末尾要带 / 因为 PROPFIND 集合资源
    assert WebDAVClient(cfg).storage_root() == "/zotero/"

def test_path_for_storage_root_empty() -> None:
    cfg = WebDAVConfig(url="https://x", storage_path="",
                       username="u", password="p", timeout=10, verify_ssl=True)
    assert WebDAVClient(cfg).storage_root() == "/"
```

- [ ] **Step 2: 实现**

```python
class WebDAVClient:
    def path_for_key(self, key: str, ext: str) -> str:
        # cfg.storage_path 已 normalize:"" 或 "/xxx"(无尾随 /)
        return f"{self._cfg.storage_path}/{key}.{ext}"

    def storage_root(self) -> str:
        # 用于 PROPFIND/MKCOL 检查 storage 目录本身
        return f"{self._cfg.storage_path}/" if self._cfg.storage_path else "/"
```

- [ ] **Step 3**:测 + commit `feat(webdav_client): add storage_path-aware path_for_key and storage_root`

---

## Task 6: webdav_client.py — HTTP 异常翻译为 CLI 错误

**Files:** Modify webdav_client.py 和 test_webdav_client.py

每个 HTTP 方法捕获 `httpx.HTTPStatusError` / `httpx.TimeoutException` / `httpx.ConnectError`,翻译为 §10.0.4 / §9.2 错误码:

| HTTP 状态 / 异常 | CLI 错误类 |
|---|---|
| 401 / 403 | `WebdavAuthFailedError` |
| 404 | 由调用方决定(DELETE 视为成功;GET/PROPFIND 视为 not exists) |
| 412(precondition fail) | `WebdavFileExistsError`(非常用,Zotero 协议用 If-None-Match 时触发) |
| 413 / 507 | `StorageQuotaExceededError`(`code="STORAGE_QUOTA_EXCEEDED"`,与 ZFS 共用) |
| 5xx 其他 | `ApiServerError`(`code="API_SERVER_ERROR"`)|
| `httpx.TimeoutException` | `WebdavTimeoutError` |
| `httpx.ConnectError` / `httpx.NetworkError` | `WebdavConnectionError` |
| `parse_prop` 抛 `WebdavPropInvalidError`（远端 `.prop` 字节不合法）| 由调用方原样向上传，不再翻译（已是 CLIError，§9.2 已加入）|

- [ ] **Step 1: 测试**(每种状态码一个 case)

```python
import respx, pytest
from httpx import Response, ConnectError, ReadTimeout
from zotero_cli.adapters.webdav_client import WebDAVClient
from zotero_cli.models.errors import (
    WebdavAuthFailedError, StorageQuotaExceededError, WebdavTimeoutError,
    WebdavConnectionError, ApiServerError,
)

@respx.mock
@pytest.mark.parametrize("status,err_cls", [
    (401, WebdavAuthFailedError),
    (403, WebdavAuthFailedError),
    (413, StorageQuotaExceededError),
    (507, StorageQuotaExceededError),
    (502, ApiServerError),
])
def test_put_status_translation(cfg, status, err_cls) -> None:
    respx.put("https://dav.example.com/zotero/X.zip").mock(return_value=Response(status))
    with pytest.raises(err_cls):
        WebDAVClient(cfg).put("/zotero/X.zip", b"x", content_type="application/zip")

@respx.mock
def test_put_timeout(cfg) -> None:
    respx.put("https://dav.example.com/zotero/X.zip").mock(side_effect=ReadTimeout("timed out"))
    with pytest.raises(WebdavTimeoutError):
        WebDAVClient(cfg).put("/zotero/X.zip", b"x", content_type="application/zip")

@respx.mock
def test_put_connect_error(cfg) -> None:
    respx.put("https://dav.example.com/zotero/X.zip").mock(side_effect=ConnectError("nope"))
    with pytest.raises(WebdavConnectionError):
        WebDAVClient(cfg).put("/zotero/X.zip", b"x", content_type="application/zip")
```

- [ ] **Step 2: 实现** — 抽 `_translate_http_error(exc: httpx.HTTPError) -> CLIError` 私有函数,在每个 HTTP 方法 try/except 中调用

```python
import httpx
from zotero_cli.models.errors import (
    WebdavAuthFailedError, StorageQuotaExceededError, WebdavTimeoutError,
    WebdavConnectionError, ApiServerError, CLIError,
)

def _translate_http_error(exc: Exception) -> CLIError:
    if isinstance(exc, httpx.TimeoutException):
        return WebdavTimeoutError("WebDAV request timed out", cause=exc)
    if isinstance(exc, httpx.ConnectError | httpx.NetworkError):
        return WebdavConnectionError(f"WebDAV connection error: {exc}", cause=exc)
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        ctx = {"http_status": code, "url": str(exc.request.url)}
        if code in (401, 403):
            return WebdavAuthFailedError("WebDAV auth failed", context=ctx, cause=exc)
        if code in (413, 507):
            return StorageQuotaExceededError(
                "WebDAV storage quota exceeded", context=ctx, cause=exc)
        return ApiServerError(f"WebDAV server error {code}", context=ctx, cause=exc)
    return ApiServerError(f"Unexpected WebDAV error: {exc}", cause=exc)
```

- [ ] **Step 3**:测 + commit `feat(webdav_client): translate HTTP errors to CLI error classes`

---

## Task 7: zotero_api.py — 扩展 attachment_simple/both/upload_attachments/Zupload 包装

**Files:**
- Modify: `src/zotero_cli/adapters/zotero_api.py`
- Test: `tests/unit/test_zotero_api_attach.py`

按设计 §10.0.2.1 表与 §10.0.2.2 命令映射表,加四个公开方法(命名直接复用 pyzotero,加类型标注与异常翻译):

| 方法 | 转发 | 用途 |
|---|---|---|
| `attachment_simple(files, parent_key)` | `Zotero.attachment_simple(files, parentid=parent_key)` | 文件名作 title 的新建 |
| `attachment_both(files_with_titles, parent_key)` | `Zotero.attachment_both(files, parentid=parent_key)` | 自定义 title 的新建 |
| `upload_attachments(templates, parent_key=None, basedir=None)` | `Zotero.upload_attachments(...)` | `--reuse-key` 走这条(`parent_key=None` 强制) |
| `zupload_with_key(template_with_key)` | `Zupload(zinst, [tpl]).upload()` | 直接调用 Zupload(`upload_attachments` 内部就是 Zupload,但有些场景需要细粒度控制) |

外加 `attachment_get(key)`(走 `Zotero.item(key)`)和 `attachment_delete(key)`(走 `Zotero.delete_item(...)`),用于 §10.3 回滚步骤。

- [ ] **Step 1: 测试**(用 pytest-mock patch pyzotero,因为返回结构 spike 已确认)

```python
from zotero_cli.adapters.zotero_api import ZoteroAPI

def test_attachment_simple_returns_pyzotero_result(mocker) -> None:
    fake_result = {"success": [{"key": "ATT1", "version": 1, "filesize": 100,
                                "md5": "x", "parentItem": "PAR1"}],
                   "failure": [], "unchanged": []}
    api = ZoteroAPI.__new__(ZoteroAPI)  # bypass __init__
    api._zot = mocker.Mock()
    api._zot.attachment_simple.return_value = fake_result
    out = api.attachment_simple(["a.pdf"], parent_key="PAR1")
    assert out == fake_result
    api._zot.attachment_simple.assert_called_once_with(["a.pdf"], parentid="PAR1")

def test_upload_attachments_forces_parent_none(mocker) -> None:
    api = ZoteroAPI.__new__(ZoteroAPI)
    api._zot = mocker.Mock()
    api._zot.upload_attachments.return_value = {"success":[], "failure":[], "unchanged":[]}
    api.upload_attachments(templates=[{"key": "ATT1", "filename": "a.pdf"}])
    # pyzotero 限制:parent_key 必须 None,适配器层保证
    api._zot.upload_attachments.assert_called_once_with(
        [{"key": "ATT1", "filename": "a.pdf"}], parentid=None, basedir=None)

def test_attachment_simple_translates_FileDoesNotExist(mocker) -> None:
    from pyzotero.zotero_errors import FileDoesNotExist
    from zotero_cli.models.errors import FileNotFoundCLIError
    import pytest
    api = ZoteroAPI.__new__(ZoteroAPI)
    api._zot = mocker.Mock()
    api._zot.attachment_simple.side_effect = FileDoesNotExist("nope")
    with pytest.raises(FileNotFoundCLIError):
        api.attachment_simple(["missing.pdf"], parent_key="X")

def test_attachment_simple_translates_RequestEntityTooLargeError(mocker) -> None:
    from pyzotero.zotero_errors import RequestEntityTooLargeError
    from zotero_cli.models.errors import StorageQuotaExceededError
    import pytest
    api = ZoteroAPI.__new__(ZoteroAPI)
    api._zot = mocker.Mock()
    api._zot.attachment_simple.side_effect = RequestEntityTooLargeError("413")
    with pytest.raises(StorageQuotaExceededError):
        api.attachment_simple(["big.pdf"], parent_key="X")
```

- [ ] **Step 2: 实现** — 在现有 `ZoteroAPI` 类上加方法,并复用阶段 3 已就位的异常翻译装饰器(若有)或新加 `_translate_pyzotero_exc()` 辅助(按 §10.0.2.6 表)

> **回应 review P2 Issue 3（adapter 公开返回 `-> dict`）**：与 Phase 2 `RawTomlDocument` 同档处理：定义 `PyzoteroResponse: TypeAlias = dict[str, Any]`（pyzotero 透传层；shape 由 pyzotero 决定，service 层用 `models/results.py` TypedDict 收紧）。adapter 公开方法签名都用此 alias，明确意图。`attachment_get` 返回 pyzotero 的 attachment item dict 同样是透传，归 `PyzoteroResponse`。

```python
from typing import Any, TypeAlias

# pyzotero 透传层；shape 由 pyzotero 决定（动态，不同 itemType 字段不同），
# 在 services/item_service.py / services/attachment_service.py 用 TypedDict 收紧。
# 边界例外见 DEVELOPMENT.md §5.2。
PyzoteroResponse: TypeAlias = dict[str, Any]
PyzoteroTemplate: TypeAlias = dict[str, Any]   # item_template(...) 输出，可带 'key' 字段


def attachment_simple(self, files: list[str], *, parent_key: str) -> PyzoteroResponse:
    try:
        return self._zot.attachment_simple(files, parentid=parent_key)
    except Exception as e:
        raise self._translate_pyzotero_exc(e) from e

def attachment_both(self, files_with_titles: list[tuple[str, str]],
                    *, parent_key: str) -> PyzoteroResponse: ...

def upload_attachments(self, *, templates: list[PyzoteroTemplate],
                       basedir: str | None = None) -> PyzoteroResponse:
    try:
        # pyzotero 限制:reuse-key 路径下 parentid 必须为 None
        return self._zot.upload_attachments(templates, parentid=None, basedir=basedir)
    except Exception as e:
        raise self._translate_pyzotero_exc(e) from e

def attachment_get(self, key: str) -> PyzoteroResponse: ...
def attachment_delete(self, key: str, *, version: int) -> None: ...
```

- [ ] **Step 3**:测 + commit `feat(zotero_api): wrap attachment_simple/both/upload_attachments per §10.0.2.2`

---

## Task 8: attachment_service.py — `_select_backend` 派发 + §10.0.1 前置校验

**Files:**
- Create: `src/zotero_cli/services/attachment_service.py`
- Create: `src/zotero_cli/models/attachment.py`
- Test: `tests/unit/test_attachment_service.py`

`_select_backend(profile)` 见设计 §10.0(profile 含 webdav 段→`"webdav"`,否则→`"zfs"`)。`attach()` 入口先做 §10.0.1 兼容性校验:`library_type=="group"` + 后端 `webdav` → 抛 `UnsupportedLibraryTypeError`。

`AttachmentResult` 用 pydantic 模型固化设计 §8.3 的统一 schema,后端不适用字段为 `None`(序列化时变 `null`)。

- [ ] **Step 1: 测试**

```python
from zotero_cli.services.attachment_service import AttachmentService, _select_backend
from zotero_cli.models.config import ProfileConfig, WebDAVConfig
from zotero_cli.models.errors import UnsupportedLibraryTypeError
import pytest

def make_profile(*, has_webdav: bool, library_type: str = "user") -> ProfileConfig:
    webdav = WebDAVConfig(url="https://x", storage_path="/zotero",
                          username="u", password="p", timeout=10, verify_ssl=True) \
             if has_webdav else None
    return ProfileConfig(api_key="k", library_id="1", library_type=library_type,
                         webdav=webdav)

def test_select_backend_no_webdav() -> None:
    assert _select_backend(make_profile(has_webdav=False)) == "zfs"

def test_select_backend_with_webdav() -> None:
    assert _select_backend(make_profile(has_webdav=True)) == "webdav"

def test_attach_group_with_webdav_rejected(mocker) -> None:
    profile = make_profile(has_webdav=True, library_type="group")
    svc = AttachmentService(profile, zotero_api=mocker.Mock(), webdav_client=mocker.Mock(),
                            audit_log_path=None)
    with pytest.raises(UnsupportedLibraryTypeError):
        svc.attach(parent_key="P", file_path="x.pdf")

def test_attach_zfs_group_allowed(mocker, tmp_path) -> None:
    # ZFS + group 是合法组合(设计 §10.0.1 矩阵第三行)
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=False, library_type="group")
    api = mocker.Mock()
    api.attachment_simple.return_value = {
        "success": [{"key": "ATT", "version": 1, "filesize": 4, "md5": "h",
                     "parentItem": "P"}],
        "failure": [], "unchanged": [],
    }
    svc = AttachmentService(profile, zotero_api=api, webdav_client=None,
                            audit_log_path=None)
    result = svc.attach(parent_key="P", file_path=str(pdf))
    assert result.backend == "zfs"
```

- [ ] **Step 2: 实现框架**

`src/zotero_cli/models/attachment.py`:
```python
from __future__ import annotations
from typing import Any, Literal, NotRequired, TypedDict
from pydantic import BaseModel, ConfigDict, Field


# 批量入参（attach_many）：与 attach() 单文件签名对齐的 keyword 集合，TypedDict 形式。
# parent_key / file_path 是必填（attach_many 内部按必填使用，见 Task 18 流水线 stage 1）；
# attach_title 才是可选项。所以用 total=True + NotRequired，避免 total=False 把必填字段
# 一起标成可选导致 type-checker 漏判。
class AttachJob(TypedDict):
    parent_key: str                     # required
    file_path: str                      # required
    attach_title: NotRequired[str]      # optional
    # reuse_key / force 不在批量路径接受（attach_many 显式拒绝），故不出现


class UploadedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    attachment_key: str
    parent_item_key: str
    size_bytes: int
    md5: str
    version: int | None = None       # ZFS 专属
    webdav_path: str | None = None   # WebDAV 专属
    mtime_ms: int | None = None      # WebDAV 专属

class FailedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    attachment_key: str | None
    parent_item_key: str
    code: str
    message: str
    context: dict[str, Any] | None = None  # 失败具体上下文（pyzotero failure[] 透传），mypy strict 需要参数化

class AttachmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["zfs", "webdav"]
    # 回应 review P3：列表字段一律用 default_factory=list，不要写 `= []`。
    # Pydantic v2 在 model 实例化时会复制类级默认值，所以 `= []` 在运行时其实是安全的；
    # 但 ruff (B008/RUF012)、mypy strict 与 reviewer 看到 mutable default 都会触发噪音
    # 警告——直接用 Field(default_factory=list) 既符合 PEP 8 / dataclass 习惯，又不破坏
    # `model_config = ConfigDict(extra="forbid")` 的 schema 校验。
    uploaded: list[UploadedItem] = Field(default_factory=list)
    unchanged: list[UploadedItem] = Field(default_factory=list)
    failed: list[FailedItem] = Field(default_factory=list)
```

`src/zotero_cli/services/attachment_service.py`:
```python
from __future__ import annotations
from pathlib import Path
from typing import Literal
from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.errors import (
    FileNotFoundCLIError, MutuallyExclusiveArgsError, UnsupportedLibraryTypeError,
)
from zotero_cli.models.attachment import AttachmentResult
from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.adapters.webdav_client import WebDAVClient


def _select_backend(profile: ProfileConfig) -> Literal["zfs", "webdav"]:
    return "webdav" if profile.webdav is not None else "zfs"


class AttachmentService:
    def __init__(self, profile: ProfileConfig, *,
                 zotero_api: ZoteroAPI, webdav_client: WebDAVClient | None,
                 audit_log_path: Path | None) -> None:
        self._profile = profile
        self._api = zotero_api
        self._webdav = webdav_client
        self._audit_log_path = audit_log_path
        self._backend = _select_backend(profile)

    def attach(self, *, parent_key: str, file_path: str,
               attach_title: str | None = None,
               reuse_key: str | None = None,
               force: bool = False) -> AttachmentResult:
        self._precheck(force=force, reuse_key=reuse_key)
        self._check_parent_and_file(parent_key=parent_key, file_path=file_path)
        if self._backend == "zfs":
            return self._attach_zfs(parent_key=parent_key, file_path=file_path,
                                     attach_title=attach_title, reuse_key=reuse_key)
        return self._attach_webdav(parent_key=parent_key, file_path=file_path,
                                    attach_title=attach_title, reuse_key=reuse_key,
                                    force=force)

    def _precheck(self, *, force: bool, reuse_key: str | None) -> None:
        """前置校验：library_type / backend / --force 互斥规则（§10.0.1, §10.0.2.3, §10.5）。

        不验证 parent / file 存在性——那是 _check_parent_and_file 的职责，
        以便批量路径在 _precheck 一次后对每个 job 单独验存活。
        """
        # §10.0.1
        if self._backend == "webdav" and self._profile.library_type == "group":
            raise UnsupportedLibraryTypeError(
                "WebDAV backend does not support group libraries",
                hint="Remove [<profile>.webdav] or use library_type=user")
        # §10.0.2.3 + §10.5:--force 仅 WebDAV 后端 + 仅 reuse_key 场景接受
        if force and self._backend == "zfs":
            raise MutuallyExclusiveArgsError(
                "--force is only supported with WebDAV backend (config has [webdav]).",
                hint=("ZFS uses md5-based idempotency. To re-upload under existing "
                      "attachment key, manually delete + recreate."))
        if force and reuse_key is None:
            raise MutuallyExclusiveArgsError(
                "--force requires --reuse-key (only meaningful for scenario B).",
                hint="--force is for forcing re-upload to existing attachment key.")

    def _check_parent_and_file(self, *, parent_key: str, file_path: str) -> None:
        """每条上传 job 都需做一次：parent item 与本地文件都存在。

        `attach()` 单文件路径在前置校验后调一次；`attach_many()` 三段流水线
        的第 1 段对每个 job 调一次。两条路径共用，签名保持一致。
        """
        if not Path(file_path).exists():
            raise FileNotFoundCLIError(
                f"Local file not found: {file_path}",
                hint="Check the path; quote it if it contains spaces.",
            )
        # parent item 存活：让 adapter 抛 ItemNotFoundError，本层不重新包
        self._api.item(parent_key)

    def _attach_zfs(self, **kw): ...     # Task 9-12
    def _attach_webdav(self, **kw): ...  # Task 13-16
```

**helper 测试**（覆盖 `_check_parent_and_file` 单元行为）：

```python
def test_check_parent_and_file_missing_local_raises(mocker, tmp_path):
    api = mocker.Mock()
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    with pytest.raises(FileNotFoundCLIError):
        svc._check_parent_and_file(parent_key="P", file_path=str(tmp_path / "nope.pdf"))
    api.item.assert_not_called()  # 文件不存在时不再打 API 探活


def test_check_parent_and_file_missing_parent_raises(mocker, tmp_path):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.item.side_effect = ItemNotFoundError("P not found")
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    with pytest.raises(ItemNotFoundError):
        svc._check_parent_and_file(parent_key="P", file_path=str(pdf))


def test_check_parent_and_file_happy_path(mocker, tmp_path):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.item.return_value = {"key": "P", "version": 1}
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    # 不抛
    svc._check_parent_and_file(parent_key="P", file_path=str(pdf))
    api.item.assert_called_once_with("P")
```

- [ ] **Step 3**:测 + commit `feat(attachment_service): add _select_backend dispatcher, _precheck (force/library_type) and _check_parent_and_file (per-job)`

---

## Task 9: attachment_service.py — ZFS 路径:`items create --attach`(场景 A)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

`items create --attach` 是 attach 之外的入口——CLI 先调用 `ItemService.create_single(payload)` 拿到 parent_key,再调 `AttachmentService.attach(parent_key, file_path, attach_title=...)`。本任务实现 ZFS 路径的 `_attach_zfs` 主体(无 `--reuse-key`),按 §10.0.2.2 命令映射:

- 有 `attach_title` → `attachment_both([(title, file)], parent_key=...)`
- 无 `attach_title` → `attachment_simple([file], parent_key=...)`

返回值映射到 `AttachmentResult`:pyzotero 的 `success` → `uploaded[]`(填 `version`,`webdav_path/mtime_ms=None`),`unchanged` → `unchanged[]`(同样映射),`failure` → `failed[]`(独立 schema)。

- [ ] **Step 1: 测试**

```python
def test_zfs_attach_simple_no_title(mocker, tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.attachment_simple.return_value = {
        "success": [{"key": "ATT", "version": 5, "filesize": 4, "md5": "h",
                     "parentItem": "PAR"}],
        "failure": [], "unchanged": [],
    }
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    r = svc.attach(parent_key="PAR", file_path=str(pdf))
    api.attachment_simple.assert_called_once_with([str(pdf)], parent_key="PAR")
    assert r.backend == "zfs"
    assert len(r.uploaded) == 1
    u = r.uploaded[0]
    assert u.attachment_key == "ATT"
    assert u.version == 5
    assert u.webdav_path is None
    assert u.mtime_ms is None

def test_zfs_attach_with_title_uses_attachment_both(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.attachment_both.return_value = {
        "success": [{"key": "A", "version": 1, "filesize": 4, "md5": "h",
                     "parentItem": "P"}],
        "failure": [], "unchanged": [],
    }
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf), attach_title="Main PDF")
    api.attachment_both.assert_called_once_with(
        [("Main PDF", str(pdf))], parent_key="P")

def test_zfs_attach_unchanged_does_not_pollute_uploaded(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.attachment_simple.return_value = {
        "success": [], "failure": [],
        "unchanged": [{"key": "A", "version": 1, "filesize": 4, "md5": "h",
                       "parentItem": "P"}],
    }
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf))
    assert r.uploaded == []
    assert len(r.unchanged) == 1
```

- [ ] **Step 2: 实现** — `_attach_zfs` + 内部 `_zfs_result_to_attachment_result()` 映射函数

- [ ] **Step 3**:测 + commit `feat(attachment_service): ZFS path for scenario A (create/update --attach without reuse-key)`

---

## Task 10: attachment_service.py — ZFS 路径:`items update --attach`(场景 A)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

`items update --attach` 与 Task 9 在 service 层等价(都是 parent_key 已存在,新建 attachment),区别仅在 CLI 命令层(Task 20)——`update` 不创建 parent。本任务的工作主要是验证测试覆盖到 `parent_key` 是已存在 item 的场景(pyzotero 不区分),并补一个父 item 探活的 service 方法(`assert_parent_exists`),用 `zotero_api.item(key)`,404 → `ItemNotFoundError`。

- [ ] **Step 1: 测试**

```python
from zotero_cli.models.errors import ItemNotFoundError
def test_attach_nonexistent_parent_raises(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.item.side_effect = ItemNotFoundError("PAR not found")
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    with pytest.raises(ItemNotFoundError):
        svc.attach(parent_key="NOPE", file_path=str(pdf))
    # 不应触达 attachment_simple
    api.attachment_simple.assert_not_called()
```

- [ ] **Step 2: 实现** — 在 `_attach_zfs` 顶部加 `self._api.item(parent_key)` 探活(异常透传 ItemNotFoundError)

- [ ] **Step 3**:测 + commit `feat(attachment_service): probe parent existence before ZFS attach (update --attach scenario)`

---

## Task 11: attachment_service.py — ZFS 路径:`items attach --reuse-key`

**Files:** Modify attachment_service.py 和 test_attachment_service.py

`--reuse-key` 走 `upload_attachments(templates=[{"key": existing, "filename": file}], parent_key=None)`(§10.0.2.4)。Service 在调 pyzotero 前先探活 `attachment_get(reuse_key)`,404→`ItemNotFoundError`。

ZFS 路径下 `--force` 已在 Task 8 precheck 拒绝,本任务无需再处理。

- [ ] **Step 1: 测试**

```python
def test_zfs_reuse_key_uses_upload_attachments(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.item.return_value = {"key": "ATT", "data": {"itemType": "attachment"}}
    api.upload_attachments.return_value = {
        "success": [{"key": "ATT", "version": 2, "filesize": 4, "md5": "h",
                     "parentItem": "P"}],
        "failure": [], "unchanged": [],
    }
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf), reuse_key="ATT")
    api.upload_attachments.assert_called_once()
    call_kw = api.upload_attachments.call_args.kwargs
    tpls = call_kw["templates"]
    assert tpls[0]["key"] == "ATT"
    assert tpls[0]["filename"] == "p.pdf"

def test_zfs_reuse_key_unchanged_returns_unchanged(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.item.return_value = {"key": "ATT"}
    api.upload_attachments.return_value = {
        "success": [], "failure": [],
        "unchanged": [{"key": "ATT", "version": 1, "filesize": 4, "md5": "h",
                       "parentItem": "P"}],
    }
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf), reuse_key="ATT")
    assert r.uploaded == []
    assert len(r.unchanged) == 1
```

- [ ] **Step 2: 实现** — 在 `_attach_zfs` 内分支:`reuse_key is not None` 时走 `upload_attachments`;先 `self._api.attachment_get(reuse_key)` 探活

- [ ] **Step 3**:测 + commit `feat(attachment_service): ZFS scenario B reuse-key via upload_attachments per §10.0.2.4`

---

## Task 12: attachment_service.py — ZFS 路径失败回滚(§10.0.2.5)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

> **回应 review P1 Issue 4**：本任务严格区分两种"失败"：
>
> - **Per-item 业务失败**（pyzotero 返回的 `failure[]` 数组中的项）→ 进 `result.failed[]`，envelope `ok=true`，因为 attach 调用本身是"完成的"。例：批量上传 5 个 PDF，其中 2 个被服务端识别为非法格式。
> - **Adapter 异常 / 整体失败**（pyzotero 抛 `StorageQuotaExceededError` / `ApiTimeoutError` / `InvalidApiKeyError` / 本地 `FileNotFoundCLIError` / `UnsupportedLibraryTypeError`）→ **不吞**，让异常透传到 command 层，runner 渲染 envelope `ok=false`，退出码非 0。这对应 DEVELOPMENT.md §4.3 错误流向。
>
> 即：**失败如果对整个调用是 fatal（attach 没法继续），就抛；失败如果只影响某一项（其他项可以继续），就进 `failed[]`**。

§10.0.2.5 表格的语义是：ZFS 路径的"父 item 已建但 attach 失败"由 commands 层处理（Task 20 的双 service 调用），AttachmentService 不直接管父 item。

本任务的工作:
1. 把 pyzotero 返回的 `failure[]` 数组中的项映射成 `FailedItem`（per-item 失败）
2. pyzotero **抛异常 → 不捕获**，让 `run_command` 在 command 层渲染 envelope failure
3. 真正抛出的情况：precheck 失败、parent 不存在、本地文件不存在、quota / timeout / auth 失败 —— 全部走 commands/ 的 `run_command` 渲染 envelope failure(`ok=false`)

**关键边界**（用 review 的话术）：`failed[]` 仅承载"未抛异常的 per-item failure"；adapter 异常不进 `failed[]`，直接透传。

- [ ] **Step 1: 测试**

```python
from zotero_cli.models.errors import StorageQuotaExceededError

def test_zfs_quota_exceeded_propagates_not_swallowed(mocker, tmp_path) -> None:
    """pyzotero 抛 StorageQuotaExceededError → service 直接透传，不进 failed[]"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF" * 100)
    api = mocker.Mock()
    api.attachment_simple.side_effect = StorageQuotaExceededError("over quota")
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    # 异常透传，不被吞进 failed[]
    with pytest.raises(StorageQuotaExceededError):
        svc.attach(parent_key="P", file_path=str(pdf))


def test_zfs_pyzotero_failure_array_mapped_to_failed(mocker, tmp_path) -> None:
    """pyzotero 不抛异常，但返回值的 failure[] 数组有内容 → 进 result.failed[]，不抛"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.attachment_simple.return_value = {
        "success": [], "unchanged": [],
        "failure": [{"key": None, "message": "Bad PDF", "code": "INVALID_FILE",
                     "filename": "p.pdf"}],
    }
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf))
    assert len(r.failed) == 1
    assert r.failed[0].code == "INVALID_FILE"
    assert r.uploaded == []
    # ok 仍为 True（envelope 层）；调用本身完成了


def test_zfs_local_file_missing_raises(mocker, tmp_path) -> None:
    """本地文件不存在 → 抛 FileNotFoundCLIError，不进 failed[]"""
    api = mocker.Mock()
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    with pytest.raises(FileNotFoundCLIError):
        svc.attach(parent_key="P", file_path="/nonexistent.pdf")
```

- [ ] **Step 2: 实现** — `_attach_zfs` 内部**不**用 try/except 包 `attachment_*` 调用；只在 `attachment_*` 返回的字典里把 `failure[]` 项映射成 `FailedItem`。adapter 抛出的 CLIError 直接透传到 command 层。

- [ ] **Step 3**:测 + commit `feat(attachment_service): ZFS path — adapter exceptions propagate, only per-item failures go to failed[]`

---

## Task 13: attachment_service.py — WebDAV 路径:完整 6 步上传(§10.2)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

按 §10.2 实现 `_attach_webdav` 主体(场景 A,无 `--reuse-key`,无 `--force`)。6 步:

| 步 | 动作 |
|---|---|
| 0 | 再次确认 `library_type=="user"`(precheck 已做,这里是 defense-in-depth) |
| 1 | 文件 / 父 item 探活(`zotero_api.item(parent_key)`、`Path.exists()`) |
| 2 | `zotero_api.create_attachment_item(parent_key, link_mode="imported_file", filename=...)` 拿 attachment key + version |
| 3 | 计算 `md5 = hashlib.md5(file).hexdigest()`、`mtime_ms = int(file.stat().st_mtime * 1000)`、调 `build_zip(file, key)`、`build_prop(md5, mtime_ms)` |
| 4 | 4a `webdav.exists(storage_root)` → 否则 `mkcol`(空 storage_path 时跳过);4b `webdav.put(<storage>/<key>.zip, zip_bytes, "application/zip")`;4c `webdav.delete(<storage>/<key>.prop)`(404 忽略);4d `webdav.put(<storage>/<key>.prop, prop_bytes, "text/xml")` |
| 5 | `zotero_api.update_attachment_md5_mtime(key, version, md5, mtime_ms)`(PATCH attachment item) |
| 6 | 构造 `UploadedItem` 加入 `uploaded[]` |

**zotero_api 在 Task 7 没加 create_attachment_item / update_attachment_md5_mtime**——本任务先在 zotero_api.py 加这两个辅助(各 5 行,薄包装 `Zotero.create_items` 和 `Zotero.update_item`),再写 service 主体。

- [ ] **Step 1: 测试**(用 respx + mock zotero_api)

```python
import respx
from httpx import Response

@respx.mock
def test_webdav_six_step_upload_happy_path(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.return_value = {"key": "ATT", "version": 5}
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    put_zip = respx.put("https://x/zotero/ATT.zip").mock(return_value=Response(201))
    respx.delete("https://x/zotero/ATT.prop").mock(return_value=Response(404))
    put_prop = respx.put("https://x/zotero/ATT.prop").mock(return_value=Response(201))

    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf))

    assert put_zip.called and put_prop.called
    api.create_attachment_item.assert_called_once()
    api.update_attachment_md5_mtime.assert_called_once()
    assert r.backend == "webdav"
    assert len(r.uploaded) == 1
    u = r.uploaded[0]
    assert u.attachment_key == "ATT"
    assert u.webdav_path == "/zotero/ATT.zip"
    assert u.mtime_ms is not None
    assert u.version is None  # WebDAV 后端字段为 null
```

- [ ] **Step 2: 实现** — `_attach_webdav` + zotero_api 加 `create_attachment_item` / `update_attachment_md5_mtime`

- [ ] **Step 3**:测 + commit `feat(attachment_service): WebDAV 6-step upload happy path per §10.2`

---

## Task 14: attachment_service.py — WebDAV 场景 B `--reuse-key` + md5 检测(§10.5)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

`items attach --reuse-key <key>` 进入场景 B:
1. 探活 attachment(`zotero_api.attachment_get(reuse_key)`,404→`ItemNotFoundError`)
2. 计算本地 md5
3. 检测远端:`exists(<storage>/<key>.prop)` → 否,`needs_reupload=True`;是,`parse_prop(get(...), source_path=<storage>/<key>.prop).hash != local_md5` → True/False。**`parse_prop` 抛 `WebdavPropInvalidError` 时直接向上传**——runner 渲染 envelope 失败（local_error，退出码 4）；不要在这里把它当成"远端有问题，重传"，因为静默覆盖损坏数据可能掩盖更深的问题。
4. **如 force=False && 远端 md5 与本地一致** → 归 `unchanged[]`,跳过 Step 4-5
5. 否则正常走 Step 4-5(§10.2)

- [ ] **Step 1: 测试**

```python
@respx.mock
def test_webdav_reuse_key_md5_match_unchanged(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"hello")
    import hashlib
    local_md5 = hashlib.md5(b"hello").hexdigest()
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.attachment_get.return_value = {"key": "ATT", "version": 1}
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/ATT.prop").mock(
        return_value=Response(207))
    respx.get("https://x/zotero/ATT.prop").mock(
        return_value=Response(200, content=(
            f'<properties version="1"><mtime>1000</mtime>'
            f'<hash>{local_md5}</hash></properties>').encode()))

    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf), reuse_key="ATT")
    assert r.uploaded == []
    assert len(r.unchanged) == 1
    assert r.unchanged[0].attachment_key == "ATT"

@respx.mock
def test_webdav_reuse_key_md5_mismatch_reuploads(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"new content")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.attachment_get.return_value = {"key": "ATT", "version": 1}
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/ATT.prop").mock(return_value=Response(207))
    respx.get("https://x/zotero/ATT.prop").mock(return_value=Response(200, content=(
        b'<properties version="1"><mtime>0</mtime>'
        b'<hash>00000000000000000000000000000000</hash></properties>')))
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    respx.put("https://x/zotero/ATT.zip").mock(return_value=Response(201))
    respx.delete("https://x/zotero/ATT.prop").mock(return_value=Response(204))
    respx.put("https://x/zotero/ATT.prop").mock(return_value=Response(201))

    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf), reuse_key="ATT")
    assert len(r.uploaded) == 1
    assert r.unchanged == []
```

- [ ] **Step 2: 实现** — `_check_remote_needs_reupload(key, local_md5) -> bool` + 在 `_attach_webdav` 内分支处理 `reuse_key`

- [ ] **Step 3**:测 + commit `feat(attachment_service): WebDAV scenario B md5 detection per §10.5`

---

## Task 15: attachment_service.py — WebDAV `--force` 语义(§10.5)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

`--force` 仅在 WebDAV + `--reuse-key` 下生效(Task 8 precheck 已拒绝其它场景):跳过 §10.5 远端 md5 检测,无条件走 Step 4-5。ZFS 后端的拒绝已在 Task 8 实现,本任务只补 WebDAV 路径下 `force=True` 时的分支与测试。

- [ ] **Step 1: 测试**

```python
@respx.mock
def test_webdav_force_skips_md5_check_and_reuploads(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"hello")
    import hashlib
    local_md5 = hashlib.md5(b"hello").hexdigest()
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.attachment_get.return_value = {"key": "ATT", "version": 1}
    webdav = WebDAVClient(profile.webdav)
    # 远端 md5 一致——但 force=True 仍重传
    propfind_storage = respx.request("PROPFIND", "https://x/zotero/").mock(
        return_value=Response(207))
    put_zip = respx.put("https://x/zotero/ATT.zip").mock(return_value=Response(201))
    respx.delete("https://x/zotero/ATT.prop").mock(return_value=Response(204))
    put_prop = respx.put("https://x/zotero/ATT.prop").mock(return_value=Response(201))
    # 关键:不 mock GET <storage>/ATT.prop,确保根本不调用(force 跳过检测)
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    r = svc.attach(parent_key="P", file_path=str(pdf), reuse_key="ATT", force=True)
    assert put_zip.called and put_prop.called
    assert len(r.uploaded) == 1

def test_zfs_force_rejected_at_precheck(mocker, tmp_path) -> None:
    # ZFS 后端 force 直接抛(Task 8 已测,这里覆盖 reuse-key 也带 force 的组合)
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"x")
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=mocker.Mock(),
                            webdav_client=None, audit_log_path=None)
    with pytest.raises(MutuallyExclusiveArgsError):
        svc.attach(parent_key="P", file_path=str(pdf), reuse_key="ATT", force=True)
```

- [ ] **Step 2: 实现** — `_attach_webdav` 内 `if force or self._check_remote_needs_reupload(...)` 决定是否重传

- [ ] **Step 3**:测 + commit `feat(attachment_service): WebDAV --force semantics per §10.5`

---

## Task 16: attachment_service.py — WebDAV 失败回滚(§10.3)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

> **回应 review P1 Issue 4**：WebDAV 路径回滚发生**之后**，原始 CLIError 必须**继续透传**（不进 `failed[]`），让 command 层的 `run_command` 渲染 envelope failure。`failed[]` 仅用于"批量上传中某一项失败但其他项继续"的情况（见 Task 17 多文件并发）。

按 §10.3 表实现单文件路径的回滚 + 透传:

| 失败位置 | 回滚动作 | 之后 |
|---|---|---|
| Step 2 创建 attachment item 失败 | 无 | 抛原异常 |
| Step 4b zip PUT 失败 | `zotero_api.attachment_delete(key, version)`（best-effort） | 抛 `WebdavConnectionError` / `WebdavTimeoutError` / `StorageQuotaExceededError` 等原异常 |
| Step 4d prop PUT 失败 | `webdav.delete(<storage>/<key>.zip)` + `attachment_delete(key, version)`（best-effort） | 抛原异常 |
| Step 5 PATCH md5/mtime 失败 | **不回滚**（zip 已上传，下次重试只补 PATCH） | 抛 `ApiServerError` |

回滚清理本身失败时只 `logging.warning` 记录、**不**改写主异常（避免淹没 root cause）。

> **关键**：单文件 `attach(parent_key, file_path)` 的失败要么完全成功（`uploaded` 一项），要么抛异常；不存在"`uploaded=[]` 且 `failed=[...]` 且 ok=true"的中间态。这种中间态只在 **多文件批量** (`attach_many`) 路径出现，见 Task 17。

- [ ] **Step 1: 测试**（验证回滚被调用 + 异常仍抛）

```python
from httpx import ConnectError

@respx.mock
def test_step4b_zip_put_failure_deletes_attachment_and_reraises(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.return_value = {"key": "ATT", "version": 1}
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    respx.put("https://x/zotero/ATT.zip").mock(side_effect=ConnectError("dropped"))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    # 异常透传，不被吞
    with pytest.raises(WebdavConnectionError):
        svc.attach(parent_key="P", file_path=str(pdf))
    # 回滚被调用
    api.attachment_delete.assert_called_once_with("ATT", version=1)


@respx.mock
def test_step4d_prop_put_failure_deletes_zip_attachment_and_reraises(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.return_value = {"key": "ATT", "version": 1}
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    respx.put("https://x/zotero/ATT.zip").mock(return_value=Response(201))
    respx.delete("https://x/zotero/ATT.prop").mock(return_value=Response(404))
    respx.put("https://x/zotero/ATT.prop").mock(side_effect=ConnectError("dropped"))
    delete_zip = respx.delete("https://x/zotero/ATT.zip").mock(return_value=Response(204))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(WebdavConnectionError):
        svc.attach(parent_key="P", file_path=str(pdf))
    assert delete_zip.called
    api.attachment_delete.assert_called_once_with("ATT", version=1)


@respx.mock
def test_step5_patch_failure_does_not_rollback_but_reraises(mocker, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.return_value = {"key": "ATT", "version": 1}
    api.update_attachment_md5_mtime.side_effect = ApiServerError("503")
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    respx.put("https://x/zotero/ATT.zip").mock(return_value=Response(201))
    respx.delete("https://x/zotero/ATT.prop").mock(return_value=Response(404))
    respx.put("https://x/zotero/ATT.prop").mock(return_value=Response(201))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(ApiServerError):
        svc.attach(parent_key="P", file_path=str(pdf))
    api.attachment_delete.assert_not_called()  # 不回滚
```

- [ ] **Step 2: 实现** — 6 步分别用 try/except 包：catch CLIError → 调对应清理 → **`raise`**（不吞异常、不进 `failed[]`）

- [ ] **Step 3**:测 + commit `feat(attachment_service): WebDAV rollback per §10.3 — exceptions propagate after cleanup`

---

## Task 17: WebDAV 并发上传(§10.4,仅 ≥2 文件)

**Files:** Modify attachment_service.py 和 test_attachment_service.py

设计 §10.4:`items create --json-file` 含多文件时,attachment items 串行创建,zip+prop 上传并发,PATCH md5/mtime 串行。本阶段实现 `attach_many(jobs: list[AttachJob])` 多文件入口；命令层 `items create --json-file` 解析 `_attachments` 后调用此入口（Task 20 Step 5），保证 service 实现可达（回应 review P2）。**仅 WebDAV 后端启用并发**:ZFS 走 pyzotero 内置批量(`attachment_simple` / `attachment_both` 已支持多文件),不并发。

并发只在**该列表 ≥2** 时启用 `ThreadPoolExecutor(max_workers=DEFAULT_PARALLEL_UPLOADS)`,单文件回退到串行(Task 13 路径)。worker 只负责 zip + prop 的 PUT 阶段（§10.2 Step 4b/4c/4d）——pyzotero 的 attachment item 创建（Step 2）和 md5/mtime PATCH（Step 5）都串行，见下文三段流水线。共享 ZoteroAPI / WebDAVClient(webdav4 同步 client 线程安全可由文档确认;如有疑问 spike Step 6 一并测)。

- [ ] **Step 1: 测试**

```python
@respx.mock
def test_webdav_concurrent_two_files(mocker, tmp_path) -> None:
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = [
        {"key": "A1", "version": 1},
        {"key": "A2", "version": 1},
    ]
    api.update_attachments_batch.return_value = {
        "success": [{"key": "A1"}, {"key": "A2"}],
        "unchanged": [],
        "failure": [],
    }
    webdav = WebDAVClient(profile.webdav)
    # 不区分顺序:两组路径都 mock
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    for k in ("A1", "A2"):
        respx.put(f"https://x/zotero/{k}.zip").mock(return_value=Response(201))
        respx.delete(f"https://x/zotero/{k}.prop").mock(return_value=Response(404))
        respx.put(f"https://x/zotero/{k}.prop").mock(return_value=Response(201))

    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    result = svc.attach_many(jobs=[
        {"parent_key": "P", "file_path": str(pdf1)},
        {"parent_key": "P", "file_path": str(pdf2)},
    ])
    assert len(result.uploaded) == 2
    assert {u.attachment_key for u in result.uploaded} == {"A1", "A2"}

def test_attach_many_single_file_does_not_use_threadpool(mocker, tmp_path) -> None:
    # 监控 ThreadPoolExecutor 不被实例化(单文件走串行)
    spy = mocker.patch("zotero_cli.services.attachment_service.ThreadPoolExecutor")
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"%PDF")
    api = mocker.Mock()
    api.attachment_simple.return_value = {
        "success": [{"key": "A", "version": 1, "filesize": 4, "md5": "h",
                     "parentItem": "P"}], "failure": [], "unchanged": []}
    svc = AttachmentService(make_profile(has_webdav=False), zotero_api=api,
                            webdav_client=None, audit_log_path=None)
    svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(pdf)}])
    spy.assert_not_called()
```

- [ ] **Step 2: 实现**（WebDAV 三段流水线）

> **回应 review P1 Issue 5**：设计 §10.4 要求三段分离：
> 1. **串行**：pyzotero 创建 attachment items（API 速率限制 + Zotero 服务端的 item 创建是串行操作）
> 2. **并发**：WebDAV `zip` 与 `prop` 上传（最多 4 并发；这是设计 §10.4 唯一开线程池的环节）
> 3. **串行**：pyzotero PATCH `md5` / `mtime`（每批 50 个 batch）
>
> 旧实现 `pool.submit(self.attach, ...)` 把所有三段都并发了，违反设计。新实现拆三段：

> **回应 review P1 Issue 4（_precheck 签名错）**：旧版 attach_many 流水线第 1 段写 `self._precheck(j.parent_key, j.file_path)`，但 `_precheck` 签名是 keyword-only `(*, force, reuse_key)`——**会 TypeError**。修订后：① 把"父 item / 本地文件存在"逻辑抽到新 helper `_check_parent_and_file(*, parent_key, file_path)`；② `attach()` 单文件路径在 `_precheck` 后调一次（先共享校验，再单文件校验），`attach_many()` 顶部一次 `_precheck(force=False, reuse_key=None)`，流水线第 1 段每个 job 调一次 `_check_parent_and_file`。两条路径用同一个 helper，签名对得上。

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import hashlib

from zotero_cli.constants import DEFAULT_PARALLEL_UPLOADS
from zotero_cli.models.errors import CLIError


@dataclass
class _UploadJob:
    """单文件的上传中间态（在三段间传递）"""
    parent_key: str
    file_path: str
    attachment_key: str | None = None   # 第 1 段填
    version: int | None = None          # 第 1 段填
    md5: str | None = None              # 第 2 段前算
    mtime_ms: int | None = None         # 第 2 段前算
    error: CLIError | None = None       # 任何段失败时填
    upload_succeeded: bool = False      # 第 2 段是否成功（决定 PATCH 是否进 batch）


def attach_many(self, *, jobs: list[AttachJob]) -> AttachmentResult:
    """Multi-file attach. Single-file or ZFS → fall back to serial self.attach().

    failed[] 边界（与 Task 12 单文件路径**严格一致**，回应 review P1 Issue 1）：

      WebDAV 批量路径下，`failed[]` **只**在 Stage 3 `update_attachments_batch`
      的 pyzotero 响应 `failure[]` 数组里产生。这是"服务端接受了 API 调用、但
      逐项业务校验拒绝某些 item"——典型的 per-item 业务失败。

      其他所有 CLIError——本地文件不存在、parent_key 不存在、auth/quota/network、
      `WebdavPropInvalidError` 等——**全部 raise**，让 command 层 run_command 渲染
      envelope failure。这与 Task 12 单文件 ZFS 路径"adapter 异常透传，不吞"语义
      完全一致；批量与单文件唯一区别仅是"批量同时操作多 item 时，pyzotero 服务端
      可能逐项接受/拒绝"。

    为什么本地 file/parent 缺失也 raise（不收集到 failed[]）？
      - 与单文件 attach() 行为一致：单 attach 抛 FileNotFoundError；批量也抛。
      - 本地 pre-flight 失败是用户的输入错误（typo / 路径错），不是"服务端只接受
        了部分"的合理 partial-progress 场景。让用户立即看到错误、修正再重跑，比
        sometimes-partial-success 的隐式行为更可预期。
      - 若用户真要"部分成功"语义，应在外部脚本里循环单文件 attach 并自己处理。
    """
    # backend / library_type / force 检查共用（单次即可，因为 attach_many 不接受 force / reuse_key）
    self._precheck(force=False, reuse_key=None)

    if len(jobs) <= 1 or self._backend == "zfs":
        # 串行：逐个 attach 并合并；任何抛出的 CLIError 直接透传（与单文件语义一致）
        merged = AttachmentResult(backend=self._backend)
        for job in jobs:
            r = self.attach(**job)
            merged.uploaded.extend(r.uploaded)
            merged.unchanged.extend(r.unchanged)
            merged.failed.extend(r.failed)
        return merged

    # WebDAV + ≥2 文件 → 三段流水线
    merged = AttachmentResult(backend="webdav")
    work_jobs = [_UploadJob(parent_key=j["parent_key"], file_path=j["file_path"]) for j in jobs]

    # 1) 串行：pyzotero create_attachment_item（每个 job 一次 API 调用，受速率限制）
    #    任何 CLIError（包括 FileNotFoundCLIError / ItemNotFoundError / 网络错 / auth 错）
    #    都直接 raise——与单文件 attach() 一致。
    for j in work_jobs:
        self._check_parent_and_file(parent_key=j.parent_key, file_path=j.file_path)
        j.md5 = hashlib.md5(Path(j.file_path).read_bytes()).hexdigest()
        j.mtime_ms = int(Path(j.file_path).stat().st_mtime * 1000)
        created = self._api.create_attachment_item(
            j.parent_key, link_mode="imported_file",
            filename=Path(j.file_path).name,
        )
        j.attachment_key = created["key"]
        j.version = created["version"]
        # 任何 CLIError 直接抛——见 docstring "为什么本地 file/parent 缺失也 raise"。
        # 已经处理过的 jobs（attachment_key 已创建）保持挂着，由用户后续修复（与
        # ZFS §10.0.2.5 "前向修复"策略一致）。

    # 2) 并发：WebDAV zip + prop PUT
    #    任何 CLIError——network / auth / quota / WebdavPropInvalidError 等——都向上抛。
    #    并发线程内的异常通过 fatal_errors 列表收集，as_completed 完成后立刻 raise；
    #    不让 stdout envelope 显示 ok=true 而事故只在 stderr 露出来。
    fatal_errors: list[CLIError] = []
    with ThreadPoolExecutor(max_workers=DEFAULT_PARALLEL_UPLOADS) as pool:
        futures = {pool.submit(self._upload_zip_and_prop, j): j for j in work_jobs}
        for fut in as_completed(futures):
            j = futures[fut]
            try:
                fut.result()
                j.upload_succeeded = True
            except CLIError as err:
                # _upload_zip_and_prop 内部已经做了回滚（删 attachment item）。
                fatal_errors.append(err)
    if fatal_errors:
        # 已并发提交的 zip 上传不回滚（与 §10.3 Step 4b "异常透传后回滚已发生"一致；
        # 失败的 job 自己内部已经清理了 attachment_item）。其他成功上传但还没 PATCH md5
        # 的 attachment 留在远端，下次 `items attach --reuse-key` 会命中 §10.5 unchanged
        # 路径仅补 PATCH。
        raise fatal_errors[0]  # 取第一个；同批通常都是同一个 root cause

    # 3) 串行：pyzotero PATCH md5/mtime（按 50 一批）。
    #    这一段是**唯一**会向 merged.failed[] 添加 per-item 失败的地方——pyzotero 的
    #    batch API 正常返回但 result['failure'] 含某项时（服务端逐项业务校验拒绝），
    #    那条 item 进 failed[]，envelope 仍 ok=true。
    self._patch_md5_mtime_batched(work_jobs, batch_size=50)

    # 汇总：第 3 段成功的 job → uploaded[]；第 3 段标记 error 的 job → failed[]
    for j in work_jobs:
        if j.error is None and j.upload_succeeded:
            merged.uploaded.append(_build_uploaded_item(j))
        elif j.error is not None:
            merged.failed.append(_build_failed_item(j))
    return merged


def _patch_md5_mtime_batched(self, jobs: list[_UploadJob], *, batch_size: int = 50) -> None:
    """Serial pyzotero update_attachments_batch (design §10.4).

    与 Task 16 单文件路径一致：
      - pyzotero 的 batch API **抛异常**（network / auth / 503 等共享失败）→ **不吞，向上抛**。
        zip 已上传但 PATCH 没完成的状态由用户后续 `items attach --reuse-key` 修复
        （远端 md5 与本地一致，命中 §10.5 场景 B unchanged，仅补 PATCH）。
      - pyzotero 的 batch API **正常返回**但单项失败（`failure[]` 数组）→ 进 `failed[]`。
        这是 per-item 业务失败，符合 review P1 Issue 4 划定的边界。

    update_attachments_batch 返回值契约（adapter 必须保证；如果 pyzotero 返回 None
    或缺字段，adapter 在翻译时填齐）：
        {"success": list[dict], "unchanged": list[dict], "failure": list[dict]}
    每个 dict 至少含 `key`；`failure` 项额外含 `code` / `message`。
    """
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        # 注意：不 catch CLIError；adapter 抛出直接向上
        result = self._api.update_attachments_batch([
            {"key": j.attachment_key, "version": j.version,
             "md5": j.md5, "mtime": j.mtime_ms}
            for j in batch
        ])
        # 处理 pyzotero 返回的 per-item failure
        from zotero_cli.models.errors import ApiServerError
        for fail in result.get("failure", []):
            failed_key = fail.get("key")
            j = next((x for x in batch if x.attachment_key == failed_key), None)
            if j is not None:
                j.error = ApiServerError(
                    fail.get("message", "PATCH md5/mtime rejected"),
                    context={"key": failed_key, "raw": fail},
                )
                j.upload_succeeded = False  # 视为本次未完成
```

**关键测试**（区分 adapter 异常 vs per-item 失败）:

```python
def test_attach_many_stage1_auth_error_aborts_whole_batch(mocker, tmp_path) -> None:
    """Stage 1：第一个 job 的 create_attachment_item 抛 InvalidApiKeyError（auth_error 类）
    → 整批 raise，不静默降级到 failed[]。"""
    files = [tmp_path / f"{i}.pdf" for i in range(3)]
    for f in files: f.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = InvalidApiKeyError("bad key")
    webdav = WebDAVClient(profile.webdav)
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(InvalidApiKeyError):
        svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(f)} for f in files])


def test_attach_many_stage1_file_missing_raises(mocker, tmp_path) -> None:
    """Stage 1：本地文件不存在（FileNotFoundCLIError）→ raise，不进 failed[]。
    与单文件 attach() 语义一致；批量唯一会进 failed[] 的是 Stage 3 pyzotero
    failure[] 响应数组。"""
    pdf_ok = tmp_path / "ok.pdf"; pdf_ok.write_bytes(b"%PDFok")
    pdf_missing = tmp_path / "missing.pdf"  # 不写
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    webdav = WebDAVClient(profile.webdav)
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(FileNotFoundCLIError):
        svc.attach_many(jobs=[
            {"parent_key": "P", "file_path": str(pdf_missing)},
            {"parent_key": "P", "file_path": str(pdf_ok)},
        ])
    # 第一个 job 在 _check_parent_and_file 即抛，create_attachment_item 不被调
    api.create_attachment_item.assert_not_called()


def test_attach_many_stage1_parent_missing_raises(mocker, tmp_path) -> None:
    """Stage 1：parent_key 不存在（ItemNotFoundError）→ raise，不进 failed[]。"""
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()

    def item_side_effect(key):
        if key == "BadParent":
            raise ItemNotFoundError(f"{key} not found")
        return {"key": key}
    api.item.side_effect = item_side_effect
    webdav = WebDAVClient(profile.webdav)
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(ItemNotFoundError):
        svc.attach_many(jobs=[
            {"parent_key": "BadParent", "file_path": str(pdf1)},
            {"parent_key": "GoodParent", "file_path": str(pdf2)},
        ])
    api.create_attachment_item.assert_not_called()


def test_attach_many_stage1_quota_exceeded_aborts_whole_batch(mocker, tmp_path) -> None:
    """Stage 1：StorageQuotaExceededError（network_error 类）→ raise，不收集到 failed[]。"""
    files = [tmp_path / f"{i}.pdf" for i in range(3)]
    for f in files: f.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = StorageQuotaExceededError("over quota")
    webdav = WebDAVClient(profile.webdav)
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(StorageQuotaExceededError):
        svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(f)} for f in files])


@respx.mock
def test_attach_many_stage2_network_error_aborts_whole_batch(mocker, tmp_path) -> None:
    """Stage 2：zip PUT 抛 WebdavConnectionError（network_error 类）→ raise。"""
    files = [tmp_path / f"{i}.pdf" for i in range(2)]
    for f in files: f.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = [
        {"key": "A0", "version": 1},
        {"key": "A1", "version": 1},
    ]
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    # 两个 job 的 zip PUT 都断网
    respx.put("https://x/zotero/A0.zip").mock(side_effect=ConnectError("dropped"))
    respx.put("https://x/zotero/A1.zip").mock(side_effect=ConnectError("dropped"))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(WebdavConnectionError):
        svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(f)} for f in files])


@respx.mock
def test_patch_batch_adapter_exception_propagates(mocker, tmp_path) -> None:
    """pyzotero batch API 抛 CLIError → 整个 attach_many 抛，不静默降级"""
    files = [tmp_path / f"{i}.pdf" for i in range(3)]
    for f in files: f.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = [
        {"key": f"A{i}", "version": 1} for i in range(3)
    ]
    api.update_attachments_batch.side_effect = ApiServerError("503 Service Unavailable")
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    for k in ("A0", "A1", "A2"):
        respx.put(f"https://x/zotero/{k}.zip").mock(return_value=Response(201))
        respx.delete(f"https://x/zotero/{k}.prop").mock(return_value=Response(404))
        respx.put(f"https://x/zotero/{k}.prop").mock(return_value=Response(201))

    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    with pytest.raises(ApiServerError):
        svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(f)} for f in files])
    # zip 不回滚（与 Task 16 §10.3 Step 5 一致）
    api.attachment_delete.assert_not_called()


@respx.mock
def test_patch_batch_per_item_failure_routed_to_failed_list(mocker, tmp_path) -> None:
    """pyzotero batch API 正常返回，但 result['failure'] 含某项 → 该项进 failed[]，
    其他项仍 uploaded[]，envelope ok=true（与 Task 16 'per-item failure' 边界一致）"""
    files = [tmp_path / f"{i}.pdf" for i in range(3)]
    for f in files: f.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = [
        {"key": f"A{i}", "version": 1} for i in range(3)
    ]
    api.update_attachments_batch.return_value = {
        "success": [{"key": "A0"}, {"key": "A2"}],
        "unchanged": [],
        "failure": [{"key": "A1", "code": "INVALID_HASH",
                     "message": "md5 doesn't match server-side blob"}],
    }
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    for k in ("A0", "A1", "A2"):
        respx.put(f"https://x/zotero/{k}.zip").mock(return_value=Response(201))
        respx.delete(f"https://x/zotero/{k}.prop").mock(return_value=Response(404))
        respx.put(f"https://x/zotero/{k}.prop").mock(return_value=Response(201))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)

    result = svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(f)} for f in files])
    assert {u.attachment_key for u in result.uploaded} == {"A0", "A2"}
    assert len(result.failed) == 1
    assert result.failed[0].attachment_key == "A1"
    assert result.failed[0].code == "API_SERVER_ERROR"
```

**Key tests**（补充并发-but-不-并发-pyzotero 的断言）：

```python
@respx.mock
def test_webdav_concurrent_pyzotero_create_called_serially(mocker, tmp_path) -> None:
    """validate: pyzotero create_attachment_item 调用顺序串行（不进线程池）"""
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}

    call_threads: list[int] = []
    def create_side_effect(*args, **kwargs):
        import threading
        call_threads.append(threading.get_ident())
        return {"key": f"A{len(call_threads)}", "version": 1}
    api.create_attachment_item.side_effect = create_side_effect

    api.update_attachments_batch.return_value = {
        "success": [{"key": "A1"}, {"key": "A2"}],
        "unchanged": [],
        "failure": [],
    }
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    for k in ("A1", "A2"):
        respx.put(f"https://x/zotero/{k}.zip").mock(return_value=Response(201))
        respx.delete(f"https://x/zotero/{k}.prop").mock(return_value=Response(404))
        respx.put(f"https://x/zotero/{k}.prop").mock(return_value=Response(201))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    svc.attach_many(jobs=[
        {"parent_key": "P", "file_path": str(pdf1)},
        {"parent_key": "P", "file_path": str(pdf2)},
    ])
    # 两次 create 在主线程；线程池只用于 zip/prop 上传
    assert len(set(call_threads)) == 1


@respx.mock
def test_webdav_concurrent_patch_called_in_batches(mocker, tmp_path) -> None:
    """validate: PATCH md5/mtime 用 update_attachments_batch（一次或分批 50），不是 per-item"""
    files = [tmp_path / f"{i}.pdf" for i in range(3)]
    for f in files: f.write_bytes(b"%PDF")
    profile = make_profile(has_webdav=True)
    api = mocker.Mock()
    api.item.return_value = {"key": "P"}
    api.create_attachment_item.side_effect = [
        {"key": f"A{i}", "version": 1} for i in range(3)
    ]
    api.update_attachments_batch.return_value = {
        "success": [{"key": "A0"}, {"key": "A1"}, {"key": "A2"}],
        "unchanged": [],
        "failure": [],
    }
    webdav = WebDAVClient(profile.webdav)
    respx.request("PROPFIND", "https://x/zotero/").mock(return_value=Response(207))
    for k in ("A0", "A1", "A2"):
        respx.put(f"https://x/zotero/{k}.zip").mock(return_value=Response(201))
        respx.delete(f"https://x/zotero/{k}.prop").mock(return_value=Response(404))
        respx.put(f"https://x/zotero/{k}.prop").mock(return_value=Response(201))
    svc = AttachmentService(profile, zotero_api=api, webdav_client=webdav,
                            audit_log_path=None)
    svc.attach_many(jobs=[{"parent_key": "P", "file_path": str(f)} for f in files])
    # 一次 batch 调用即可（3 < 50）
    assert api.update_attachments_batch.call_count == 1
    args = api.update_attachments_batch.call_args[0][0]
    assert {a["key"] for a in args} == {"A0", "A1", "A2"}
```

- [ ] **Step 3**:测 + commit `feat(attachment_service): WebDAV 3-stage pipeline (serial create / parallel upload / batched PATCH) per §10.4`

---

## Task 18: envelope schema 统一(§8.3)

**Files:**
- Test: `tests/unit/test_attachment_service.py`(envelope schema 断言)
- 可能 Modify: `src/zotero_cli/models/attachment.py`(若发现字段缺失)

本任务不写新代码,只**校验**之前任务交付的 `AttachmentResult` 序列化后(`model_dump(mode="json", exclude_none=False)`)严格符合设计 §8.3 约束:

- `data.backend` ∈ `{"zfs", "webdav"}`
- `data.uploaded[]` 与 `data.unchanged[]` **字段集完全一致**:`file / attachment_key / parent_item_key / size_bytes / md5 / version / webdav_path / mtime_ms`(ZFS 后端 `webdav_path/mtime_ms=null`;WebDAV 后端 `version=null`)
- `data.failed[]` 用**独立** schema:`file / attachment_key(可 null)/ parent_item_key / code / message / context`,**不**含 size_bytes / md5 / version / webdav_path / mtime_ms

> **回应 review P3(命令层与 schema 测试 dump 参数对齐)**:命令层(Task 20)统一调
> `result.model_dump(mode="json", exclude_none=False)`。本 Task 的 schema 断言测试**必须用同样的参数**——`mode="json"` 让所有字段的 JSON 形态(datetime / Path 等)与命令真实输出一致;`exclude_none=False` 强制"不适用字段输出 null,不省略 key",这正是设计 §8.3「字段总存在原则」要求的、agent 友好的稳定 schema。pydantic 默认 `exclude_none=False`,但显式声明可以防止后续 `model_config` 改成 `exclude_none=True` 时本测试**还能过**——锁住命令层与本测试的语义一致。

- [ ] **Step 1: 测试**

```python
DUMP_KWARGS = {"mode": "json", "exclude_none": False}   # 与 Task 20 命令层完全一致

def test_zfs_uploaded_has_full_field_set_with_nulls(mocker, tmp_path) -> None:
    # 跑一遍 Task 9 的 happy path,然后 dump 检查 keys
    ...
    dumped = result.model_dump(**DUMP_KWARGS)
    upload_keys = set(dumped["uploaded"][0].keys())
    assert upload_keys == {
        "file", "attachment_key", "parent_item_key", "size_bytes", "md5",
        "version", "webdav_path", "mtime_ms",
    }
    assert dumped["uploaded"][0]["webdav_path"] is None
    assert dumped["uploaded"][0]["mtime_ms"] is None

def test_webdav_uploaded_has_full_field_set_with_nulls(...) -> None:
    # 类似,断言 version is None,webdav_path/mtime_ms 非空
    dumped = result.model_dump(**DUMP_KWARGS)
    assert dumped["uploaded"][0]["version"] is None

def test_unchanged_same_schema_as_uploaded(...) -> None:
    dumped = result.model_dump(**DUMP_KWARGS)
    assert set(dumped["unchanged"][0].keys()) == set(dumped["uploaded"][0].keys())

def test_failed_independent_schema(mocker, tmp_path) -> None:
    # 跑一个失败场景,检查 failed[0] 仅含约定字段
    dumped = result.model_dump(**DUMP_KWARGS)
    failed_keys = set(dumped["failed"][0].keys())
    assert failed_keys == {
        "file", "attachment_key", "parent_item_key", "code", "message", "context",
    }
    # 不应含 size_bytes / md5 / version / webdav_path / mtime_ms
    assert "size_bytes" not in failed_keys
```

- [ ] **Step 2**:跑测试,如失败 → 补 `models/attachment.py` 字段(确保 `UploadedItem` / `UnchangedItem` / `FailedItem` 的字段集与 §8.3 表完全一致;不适用字段写成 `Optional[T] = None`,不要从 model 里移除)。**不要**通过给 `model_config` 加 `exclude_none=True` 来"绕过"测试——这会让命令层 dump 出来的 envelope 丢掉 null 字段,违反设计 §8.3。

- [ ] **Step 3**:测 + commit `test(attachment_service): assert envelope schema unified per §8.3 (with mode=json, exclude_none=False)`

---

## Task 19: meta.affected_keys 计算规则(§8.3.1)

**Files:**
- Modify: `src/zotero_cli/services/attachment_service.py`(加 `affected_keys` 辅助)
- Test: `tests/unit/test_attachment_service.py`

§8.3.1 表:

| 来源 | 进 `affected_keys` |
|---|---|
| 新创建父 item key(`items create --attach`) | ✅ |
| 新创建 attachment item key(`uploaded[]`) | ✅ |
| `--reuse-key` 重传成功的 attachment(`uploaded[]`) | ✅ |
| `unchanged[]` 中的 attachment | ❌ |
| `failed[]` 中的 attachment | ❌ |

新建父 item key 不在 `AttachmentResult` 内(由 Phase 3 `ItemService.create_single(payload)` 返回,在命令层合并)。Service 层只负责返回 `attachment` 部分的 affected_keys。

- [ ] **Step 1: 测试**

```python
def test_affected_keys_includes_only_uploaded(mocker, tmp_path) -> None:
    # 1 uploaded + 1 unchanged + 1 failed → affected_keys 只含 uploaded 那个
    ...
    keys = result.affected_keys()
    assert keys == ["ATT_UPLOADED"]
    assert "ATT_UNCHANGED" not in keys
    assert "ATT_FAILED" not in keys

def test_affected_keys_empty_when_only_unchanged(...) -> None:
    keys = result.affected_keys()
    assert keys == []
```

- [ ] **Step 2: 实现** — 在 `AttachmentResult` 类上加方法

```python
class AttachmentResult(BaseModel):
    ...
    def affected_keys(self) -> list[str]:
        return [u.attachment_key for u in self.uploaded]
```

命令层把 `AttachmentResult.affected_keys()` 与新建父 item key(若有)合并,塞进 `Envelope.success(meta_extra={"affected_keys": [...], "backend": result.backend})`。

- [ ] **Step 3**:测 + commit `feat(attachment_service): affected_keys computation per §8.3.1`

---

## Task 20: commands/items.py — `--attach` 选项 + `attach` 子命令(含 audit_log)

**Files:**
- Modify: `src/zotero_cli/commands/items.py`
- Test: `tests/unit/test_commands_items_attach.py`(或扩展现有 test_commands_items)

加 CLI 层布线:

| 命令 | 选项 |
|---|---|
| `items create --attach <file> [--attach-title <t>] [--dry-run]` | 创建父 item → `attachment_service.attach(parent_key=new, file_path=file, attach_title=t)`；父建成功但 attach 失败时，父 key 放在 `error.context.parent_item_key` |
| `items update <key> --attach <file> [--attach-title <t>] [--dry-run]` | `attachment_service.attach(parent_key=key, file_path=file, attach_title=t)`；若 metadata 已更新后 attach 失败，`error.context.metadata_updated=true` |
| `items attach <parent> <file> [--title <t>] [--reuse-key <k>] [--force] [--dry-run]` | `attachment_service.attach(parent_key=parent, file_path=file, attach_title=title, reuse_key=k, force=force)` |

> **回应 review P1（不绕过既有 runner 路径）**：本 Task 的所有命令**一律复用 Phase 3 Task 9 已实现的 `_invoke_write` helper**——它已经包到了 `run_command` 内部，自动获得：
> ① 全局 `--json` + `--quiet` mutex（设计 §7.2 / Phase 2 Task 6b）
> ② 统一 `CLIError` 捕获 → envelope failure 渲染（设计 §7.5）
> ③ 默认模式错误 → stderr / `--json` 模式错误 → stdout 的流向区分
> ④ audit-on-error（service 抛 CLIError → 写 `result="failure"` 审计条目）
>
> 命令体内**禁止**手写 `Envelope.success(...)` + `output.render(...)`、**禁止**自己 `try/except CLIError`、**禁止**自己写 stdout/stderr。原版方案绕开了这条架构纪律（P1 review issue）。
>
> **回应 review P3（model_dump 参数固定）**：service 返回的 `AttachmentResult` 在命令层进 envelope `data` 时，**统一**调
> ```python
> result.model_dump(mode="json", exclude_none=False)
> ```
> `mode="json"` 让 datetime / Decimal 等显式可序列化；`exclude_none=False` 强制 `version`/`webdav_path`/`mtime_ms`/`uploaded[].attachment_key` 等"不适用字段输出 null"（设计 §8.3「字段总存在原则」）。如果未来 pydantic 默认行为或某个 model `model_config` 改变，schema 不会漂移。Task 18 的 schema 断言测试也按这套调用方式跑。

### Action 闭包契约

`_invoke_write(action=...)` 期望 `action() -> tuple[Any, dict[str, Any] | None]`，即 `(envelope_data, meta_extra)`。本 Task 三个命令的 `action` 实现规则统一如下：

```python
def action() -> tuple[Any, dict[str, Any] | None]:
    # 1) 加载 profile（不在 action 外做，确保 ConfigError 也能被 _invoke_write 抓到 audit）
    profile = load_config(profile=options.profile, config_path=options.config_path)
    api = ZoteroAPI(profile)
    svc = AttachmentService(profile, zotero_api=api,
                            webdav_client=_maybe_webdav(profile),
                            audit_log_path=None)  # audit 由 _invoke_write 统一管

    # 2) 调 service.attach(...) — 任何 adapter / precheck 异常透传给 _invoke_write
    result = svc.attach(parent_key=..., file_path=..., ...)

    # 3) data 用 mode="json", exclude_none=False 固化 schema（设计 §8.3 / review P3）
    data = result.model_dump(mode="json", exclude_none=False)

    # 4) meta_extra：affected_keys + backend
    affected = list(result.affected_keys())  # service 端只含 attachment 部分
    meta_extra = {"backend": result.backend, "affected_keys": affected}
    return data, meta_extra
```

`partial_failure` 审计语义：当 `result.failed` 非空时，进 envelope 的仍是 `ok=true`（per-item 失败，不是整体异常 — 设计 §10.0.2.5 A3 / Task 12 边界），但**审计条目**应该写 `result="partial_failure"`。`_invoke_write` 当前只区分 `success` / `failure`（CLIError 抛出走 failure 路径），所以 Task 9 helper 需要扩一个钩子让 `action` 能反馈"成功 + 部分失败"。最小改动：在 Task 20 的 step 1 之前，先扩 `_invoke_write` 签名，后做 attach 命令实现。

### Step 0:扩 `_invoke_write` 支持 `partial_failure` 审计语义 + 命令自定义 dry-run payload

**File:** `src/zotero_cli/commands/items.py`

**Change**：在 Phase 3 Task 9 已定义的 `_invoke_write` 基础上做两个向后兼容扩展：
1. `action()` 可选返回第三个 tuple 元素 `audit_status: Literal["success", "partial_failure"]`。`_invoke_write` 在 success 路径写审计时使用该值；CLIError 路径仍写 `"failure"`。
2. 保留 Phase 3 的 `dry_run_data` 可选 kwarg，让附件命令按 spec §8.4 返回 `would_upload` / `would_create`，而不是固定 `{"dry_run": True}`。

```python
ActionResult = (
    tuple[Any, dict[str, Any] | None]
    | tuple[Any, dict[str, Any] | None, Literal["success", "partial_failure"]]
)
DryRunActionResult = tuple[Any, dict[str, Any] | None]


def _invoke_write(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    action: Callable[[], ActionResult],
    *,
    args_for_audit: dict[str, Any],
    dry_run: bool = False,
    dry_run_data: Callable[[], DryRunActionResult] | None = None,
) -> None:
    ...
    def wrapped() -> Any:
        start_ns = time.perf_counter_ns()
        try:
            if dry_run:
                if dry_run_data is None:
                    data: Any = {"dry_run": True}
                    meta_extra: dict[str, Any] | None = {"dry_run": True}
                else:
                    data, meta_extra = dry_run_data()
                captured_meta.update(meta_extra or {"dry_run": True})
                return data
            ret = action()
            if len(ret) == 2:
                data, meta_extra = ret
                audit_status: Literal["success", "partial_failure"] = "success"
            else:
                data, meta_extra, audit_status = ret
            elapsed = (time.perf_counter_ns() - start_ns) // 1_000_000
            captured_meta.update(meta_extra or {})
            write_entry(log_path=log_path, entry=AuditEntry(
                timestamp=now_iso(), profile=options.profile, command=command,
                args=args_for_audit, result=audit_status,
                affected_keys=(meta_extra or {}).get("affected_keys", []),
                elapsed_ms=elapsed,
            ))
            return data
        except CLIError as err:
            ...  # 不变，写 result="failure"
```

> 这个改动属于 Phase 3 helper 的最小延展，不破坏 Phase 3 的写命令（它们仍返 2-tuple，命中 `audit_status="success"` 默认分支；不传 `dry_run_data` 时仍返回 `{"dry_run": True}`）。

- [ ] **Step 0a:测**

```python
def test_invoke_write_records_partial_failure_when_action_returns_tag(...) -> None:
    """action 返 ('data', meta, 'partial_failure') → audit 写 'partial_failure'"""
    # 用 _invoke_write 跑一个返 3-tuple 的 stub action，断言 audit JSONL 中 result='partial_failure'


def test_invoke_write_uses_custom_dry_run_data_without_audit(...) -> None:
    """dry_run=True + dry_run_data → envelope data 使用 would_upload，且不写 audit"""
    # dry_run_data 返回 ({"dry_run": True, "would_upload": [...]}, {"dry_run": True})
    # 断言 stdout envelope.data 含 would_upload，action 没被调用，audit 文件为空
```

- [ ] **Step 0b:实现 + 跑测**

- [ ] **Step 0c:commit** `refactor(commands/items): extend _invoke_write for partial audit and dry-run payloads`

---

### Step 1: 实现 `items attach` 子命令(独立命令,无 partial-create 风险)

`items attach <parent> <file> [--title <t>] [--reuse-key <k>] [--force] [--dry-run]`：单一 service 调用，无父 item 副作用，最干净。

> **回应 review P1（全失败必须非零退出）**：design §10.0.2.5 B2 / C 明文规定单文件路径下 `failed[]` 非空且 `uploaded[]/unchanged[]` 均为空时**全失败退 2**（沿 `failed[0].code` 映射）。Task 12 也明确"单文件 attach 不存在 `uploaded=[] 且 failed=[...] 且 ok=true` 的中间态"。Service 层为了与多文件 `attach_many` schema 统一会返回 `AttachmentResult(failed=[...])`，命令层负责把"全失败"翻译成 envelope failure：抛 `failed[0]` 携带的 CLIError，由 `_invoke_write` → `run_command` 走标准 failure 路径。引入命令层私有 helper：
>
> ```python
> from zotero_cli.models.attachment import AttachmentResult
> from zotero_cli.models.errors import from_code
>
>
> def _raise_if_total_attachment_failure(result: AttachmentResult) -> None:
>     """All-failure → raise the first failed item's CLIError so _invoke_write 渲染 envelope failure.
>
>     "全失败"= uploaded[] 与 unchanged[] 均为空、failed[] 非空。多文件路径下 uploaded
>     或 unchanged 任一非空就视为部分成功，envelope 仍 ok=true（A4 / Task 17）。
>     """
>     if result.failed and not result.uploaded and not result.unchanged:
>         first = result.failed[0]
>         raise from_code(
>             first.code, first.message,
>             context={
>                 "file": first.file,
>                 "parent_item_key": first.parent_item_key,
>                 "attachment_key": first.attachment_key,
>                 **(first.context or {}),
>             },
>         )
> ```

```python
@app.command("attach")
def cmd_attach(
    ctx: typer.Context,
    parent_key: str = typer.Argument(..., help="Parent item key"),
    file_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                     help="Local file to upload as attachment"),
    title: str | None = typer.Option(None, "--title",
                                     help="Attachment item title (default = filename)"),
    reuse_key: str | None = typer.Option(None, "--reuse-key",
                                         help="Reuse existing attachment item key"),
    force: bool = typer.Option(False, "--force",
                               help="WebDAV only: skip remote md5 check before upload"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    options: GlobalOptions = ctx.obj

    def dry_run_data() -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "dry_run": True,
            "would_upload": [{
                "parent_item_key": parent_key,
                "file": str(file_path),
                "title": title or file_path.name,
                "reuse_key": reuse_key,
                "force": force,
            }],
        }, {"dry_run": True, "affected_keys": []}

    def action() -> tuple[Any, dict[str, Any], Literal["success", "partial_failure"]]:
        profile = load_config(profile=options.profile, config_path=options.config_path)
        api = ZoteroAPI(profile)
        svc = AttachmentService(profile, zotero_api=api,
                                webdav_client=_maybe_webdav(profile),
                                audit_log_path=None)
        result = svc.attach(parent_key=parent_key, file_path=str(file_path),
                            attach_title=title, reuse_key=reuse_key, force=force)
        # 回应 review P1：全失败必须非零退出（design §10.0.2.5 B2 / C）。
        # uploaded[] 与 unchanged[] 均为空、failed[] 非空 → 抛第一条 CLIError，
        # _invoke_write 渲染 envelope failure，退码沿 failed[0].code 映射。
        _raise_if_total_attachment_failure(result)
        data = result.model_dump(mode="json", exclude_none=False)
        meta_extra = {"backend": result.backend,
                      "affected_keys": list(result.affected_keys())}
        status: Literal["success", "partial_failure"] = (
            "partial_failure" if result.failed else "success"
        )
        return data, meta_extra, status

    _invoke_write(
        ctx, command="items.attach", mode=OutputMode.SUMMARY,
        action=action,
        args_for_audit={
            "parent_key": parent_key, "file": str(file_path),
            "title": title, "reuse_key": reuse_key, "force": force,
        },
        dry_run=dry_run,
        dry_run_data=dry_run_data,
    )
```

### Step 2: 实现 `items update --attach`(无父建,语义同 attach)

`items update <key> --attach <file> [--attach-title <t>] [--dry-run]` 的 attach 路径与上面一致；本 Task 新加 `--attach` / `--attach-title` / `--dry-run` 选项，**当 `--attach` 为 None 时走 Phase 3 Task 9 既有 `update` 路径**（不动）。当 `--attach` 不为 None 但 `update` 也带了 metadata flag（`--title` / `--tags` / `--json-patch`），按设计 §6 命令树规则：**两步顺序执行**——先做 metadata update（拿 `update_result`），再做 attach（拿 `attach_result`），合并 affected_keys。attach 抛 CLIError 时保持 `data=null`，把 `parent_item_key` / `metadata_updated` 放进 `error.context`（见 Step 4）。本 Step 覆盖"`--attach` 单独使用"的路径；同时带 metadata 的合成路径单独写 Step 4。

action 闭包骨架（仅 attach 的 update 路径）：

```python
def action() -> tuple[Any, dict[str, Any], Literal["success", "partial_failure"]]:
    profile = load_config(profile=options.profile, config_path=options.config_path)
    api = ZoteroAPI(profile)
    attach_svc = AttachmentService(profile, zotero_api=api,
                                   webdav_client=_maybe_webdav(profile),
                                   audit_log_path=None)

    try:
        result = attach_svc.attach(parent_key=key, file_path=str(attach),
                                   attach_title=attach_title)
    except CLIError as err:
        # 父 item 是用户传入的既有 key；不是本次新建——parent_created=False
        # 防止 agent 把 update 路径下的失败误判为"可删除回滚"。
        raise _with_attachment_context(
            err, parent_key=key, parent_created=False,
        ) from err

    # 全失败(uploaded[]/unchanged[] 均空 + failed[] 非空)→ envelope failure 退非零
    # design §10.0.2.5 B2 要求 "全失败退 2，部分失败退 0"。failed[0].code 决定退码。
    if result.failed and not result.uploaded and not result.unchanged:
        first = result.failed[0]
        err = from_code(
            first.code, first.message,
            context={"file": first.file, "parent_item_key": first.parent_item_key,
                     "attachment_key": first.attachment_key, **(first.context or {})},
        )
        raise _with_attachment_context(err, parent_key=key, parent_created=False)

    data = result.model_dump(mode="json", exclude_none=False)
    meta_extra = {"backend": result.backend,
                  "affected_keys": list(result.affected_keys())}
    status: Literal["success", "partial_failure"] = (
        "partial_failure" if result.failed else "success"
    )
    return data, meta_extra, status
```

### Step 3: 实现 `items create --attach`(含 §10.0.2.5 A2/A3 partial state)

> **回应 review P1（partial state）**：`Envelope` 在 spec §8.5 与 Phase 1 Task 6 中明确保持 `ok=false ⇒ data=null`。因此 A2 不改变 failure envelope 不变量，也不在错误对象上动态挂载额外 data。父 item key 通过 `error.context.parent_item_key` 暴露，仍走 `_invoke_write` → `run_command` 的标准 failure 路径。
>
> **回应 review P1（全失败必须非零退出）**：design §10.0.2.5 B2 / C 明文规定 `items update --attach` / `items attach` 在 pyzotero 返回 `failure[]` 非空且 `uploaded=[]` 时 **全失败退 2**，只有 `uploaded` 非空的"部分失败"才退 0。原版 A3 行写"exit 0"违反此规定（`items create --attach` 应与 update / attach 全失败语义对齐——父 item 已建出来这一点通过 `error.context.parent_created=true` 暴露给 agent，不靠退 0 来传达）。修订后 A3 与 update / attach 全失败统一走 `_raise_if_total_attachment_failure()` 把 `failed[0]` 的 CLIError 抛出，由 `_invoke_write` 渲染 envelope failure，退码沿 `failed[0].code` 映射（参见 design §9 错误码映射表）。
>
> 修订后语义（与设计 §10.0.2.5 表一致）：
>
> | 失败位置 | envelope | exit_code | agent 可读字段 |
> |---|---|---|---|
> | A1. 父 item 创建失败 | `ok=false`、`data=null`，`error.code` 由 `ItemService.create_single` 透传 | 1-4 | 无 `parent_item_key`（父 item 没建出来） |
> | A2. 父建成功 + attach 抛 CLIError(`StorageQuotaExceededError` / `ApiTimeoutError` / `WebdavConnectionError` / ...) | `ok=false`、`data=null`，保留原错误码和 exit_code | 1-4 | `error.context.parent_created=true`、`error.context.parent_item_key="<new_key>"`、`error.context.attachment_uploaded=false`、`error.context.attachment_error={code, message}` |
> | A3. 父建成功 + attach 完成但 `failed[]` 非空、`uploaded[]` / `unchanged[]` 均为空（全失败） | `ok=false`、`data=null`，`error.code = failed[0].code`（INVALID_FILE / API_SERVER_ERROR / ...） | 1-4 | `error.context.parent_created=true`、`error.context.parent_item_key="<new_key>"`、`error.context.attachment_uploaded=false`、`error.context.attachment_error={code, message}` |
> | A4. 父建成功 + attach 部分成功（`uploaded[]` / `unchanged[]` 非空 且 `failed[]` 也非空，仅多文件 `--json-file` 路径产生） | `ok=true`，envelope 是 per-item partial success | 0 | `data.parent_created=true`、`data.parent_item_key="<new_key>"`、`data.attachment_uploaded=true`、完整 `AttachmentResult` 字段；audit `result="partial_failure"` |
> | 全成功 | `ok=true` | 0 | `data.parent_created=true`、`data.parent_item_key="<new_key>"`、`data.attachment_uploaded=true`、完整 `AttachmentResult` 字段 |
>
> A2 / A3 的错误封装只增强 `context`，不新增错误码。这样不会破坏 spec §8.5、Phase 1 envelope invariant 或 Phase 2 fallback JSON（fallback 仍固定 `data: null`）。

`items create --attach` 的 action 实现：

```python
from zotero_cli.models.errors import CLIError, from_code


def _with_attachment_context(err: CLIError, *, parent_key: str,
                             parent_created: bool,
                             metadata_updated: bool | None = None) -> CLIError:
    """Wrap a service-layer CLIError with partial-state context for command-layer envelopes.

    回应 review P1（parent_created 必须按调用路径区分，不能写死 True）：
      - `items create --attach` 的 A2 失败路径：父 item 是**本次刚刚创建出来**的
        (`parent_created=True`)，agent 看到这个标志才会去做"删父 item 回滚"或
        "items attach 续传"决策。
      - `items update --attach` 的失败路径：父 item 是**调用前就存在**的
        (`parent_created=False`)，agent 绝不能把它当新建物来"回滚删除"——那会
        误删用户既有数据。
      - 因此 `parent_created` 必须由 caller 显式传，**不能在本 helper 里硬编码 True**。

    `metadata_updated` 仅在"`items update --attach` 同时带 metadata flag"的合成路径
    使用——区分"metadata 已 patch 但 attach 失败"与"两步都没做"。`items create --attach`
    与"仅 attach"的 update 路径都不传该 kwarg。
    """
    context = {
        **err.context,
        "parent_created": parent_created,
        "parent_item_key": parent_key,
        "attachment_uploaded": False,
        "attachment_error": {"code": err.code, "message": err.message},
    }
    if metadata_updated is not None:
        context["metadata_updated"] = metadata_updated
    return from_code(err.code, err.message, hint=err.hint, context=context, cause=err)


@app.command("create")
def cmd_create(
    ctx: typer.Context,
    item_type: str | None = typer.Option(None, "--type"),
    title: str | None = typer.Option(None, "--title"),
    # ... 其他 Phase 3 既有选项
    attach: Path | None = typer.Option(None, "--attach", exists=True, dir_okay=False),
    attach_title: str | None = typer.Option(None, "--attach-title"),
    json_file: Path | None = typer.Option(None, "--json-file", exists=True, dir_okay=False),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    options: GlobalOptions = ctx.obj
    # 路径分派（review P2 修复：原版只走 attach 单文件路径，json_file 是哑参数；
    # 这里恢复 json_file 路径并把它接到 attach_many——见 Step 5）：
    #   1. --json-file 与 --attach 互斥（design §6 / Phase 3 已有此约束；此处再次防御）
    #   2. --json-file → 批量路径，含多附件时调 attach_many()
    #   3. --attach → 单 attach 路径（下文）
    #   4. 都没有 → Phase 3 既有 _cmd_create_without_attach
    if json_file is not None and attach is not None:
        raise MutuallyExclusiveArgsError(
            "--json-file and --attach are mutually exclusive",
            hint="Put per-item attachments in the JSON file's `_attachments` array; "
                 "see Phase 4 Task 20 Step 5.",
        )
    if json_file is not None:
        return _cmd_create_json_file_with_attachments(
            ctx, json_file=json_file, dry_run=dry_run, options=options,
        )
    if attach is None:
        # 无 attach → 走 Phase 3 既有路径（不动）
        return _cmd_create_without_attach(ctx, ...)

    payload = _build_create_payload(item_type=item_type, title=title, ...)

    def dry_run_data() -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "dry_run": True,
            "would_create": [payload],
            "would_upload": [{"parent_item_key": None,
                               "file": str(attach),
                               "title": attach_title or attach.name}],
        }, {"dry_run": True, "affected_keys": []}

    def action() -> tuple[Any, dict[str, Any], Literal["success", "partial_failure"]]:
        profile = load_config(profile=options.profile, config_path=options.config_path)
        api = ZoteroAPI(profile)
        item_svc = ItemService(api)
        attach_svc = AttachmentService(profile, zotero_api=api,
                                       webdav_client=_maybe_webdav(profile),
                                       audit_log_path=None)

        # A1: create_single 失败会抛 CLIError；_invoke_write 标准 failure 路径保持 data=null。
        parent_item = item_svc.create_single(payload)
        parent_key = parent_item["key"]

        try:
            attach_result = attach_svc.attach(
                parent_key=parent_key, file_path=str(attach), attach_title=attach_title,
            )
        except CLIError as err:
            # A2: 父 item 已创建；保持顶层 data=null，把可恢复信息放进 error.context。
            # parent_created=True：本次刚刚 create_single 出来的父 item，agent 可决定
            # 删除回滚或续传。
            raise _with_attachment_context(
                err, parent_key=parent_key, parent_created=True,
            ) from err

        # A3: 父建成功 + 全失败（uploaded[]/unchanged[] 均空 & failed[] 非空）→
        # 把 failed[0] 的 CLIError 抛出，error.context 仍带 parent_created=True，
        # 让 agent 知道父 item 还在远端。design §10.0.2.5 B2 / C 要求"全失败退非零"。
        if attach_result.failed and not attach_result.uploaded and not attach_result.unchanged:
            first = attach_result.failed[0]
            err = from_code(
                first.code, first.message,
                context={
                    "file": first.file,
                    "parent_item_key": first.parent_item_key,
                    "attachment_key": first.attachment_key,
                    **(first.context or {}),
                },
            )
            raise _with_attachment_context(
                err, parent_key=parent_key, parent_created=True,
            )

        # 全成功 / A4 per-item partial success（uploaded 或 unchanged 非空 + failed 也非空）
        partial = bool(attach_result.failed)
        data = {
            "parent_created": True,
            "parent_item_key": parent_key,
            "attachment_uploaded": bool(attach_result.uploaded),
            **attach_result.model_dump(mode="json", exclude_none=False),
        }
        meta_extra = {
            "backend": attach_result.backend,
            "affected_keys": [parent_key, *attach_result.affected_keys()],
        }
        status: Literal["success", "partial_failure"] = (
            "partial_failure" if partial else "success"
        )
        return data, meta_extra, status

    _invoke_write(
        ctx, command="items.create", mode=OutputMode.SUMMARY,
        action=action,
        args_for_audit={
            "type": item_type, "title": title, "attach": str(attach),
            "attach_title": attach_title,
        },
        dry_run=dry_run,
        dry_run_data=dry_run_data,
    )
```

> **设计 §10.0.2.5 一致性**：A2 路径下 `error.context.parent_item_key` 让 agent 能跑 `zotero-cli items delete <pk>` 回滚或 `zotero-cli items attach <pk> <file>` 续传；同时顶层 `data` 仍为 `null`，符合 spec §8.5 与 Phase 1 invariant。

### Step 4: `items update --attach` 同时带 metadata flag 的合成路径

如果用户 `items update <key> --title "T" --attach p.pdf`：先 update metadata（`item_svc.update`），再 attach。失败语义同上，但 `parent_key` 是用户传入的 `<key>`（已存在），没有"父建成功"问题——只有"metadata 改成功 / attach 失败"或反之。最简实现：
- metadata update 抛 CLIError → 标准 failure 路径，envelope `data=null`（attach 没动）
- metadata update 成功，attach 抛 CLIError → 重新抛同错误码的 CLIError，**`error.context.parent_created=false`**（父 item 是既有 item，不是本次新建——见下方实现），`error.context.parent_item_key=<key>`、`error.context.metadata_updated=true`、`error.context.attachment_uploaded=false`
- metadata update 成功，attach 完成但**全失败**（`uploaded[]/unchanged[]` 均空 + `failed[]` 非空）→ 同上，把 `failed[0]` 的 code 包成 CLIError 抛出，`error.context.metadata_updated=true`、`parent_created=false`
- 全成功 → 合并 affected_keys = `[<key>] + attach.affected_keys()`

注：metadata 与 attach 都走 patch（不是 create）。只有 metadata 已 patch 成功后，attach 错误才会带 `metadata_updated=true`。

> **回应 review P1（`parent_created` 不能在 update 路径误标 True）**：原版 `_with_attachment_context()` 把 `parent_created=True` 写死，会让 update 路径的 `error.context` 谎称"父 item 是新建的"，agent 据此可能做删除回滚操作，**误删用户既有数据**。修订后 helper 把 `parent_created` 提为必填 keyword：
>
> | 路径 | helper 调用 | `error.context.parent_created` |
> |---|---|---|
> | `items create --attach` A2 | `_with_attachment_context(err, parent_key=new_key, parent_created=True)` | `True` |
> | `items update --attach`（仅 attach） | `_with_attachment_context(err, parent_key=key, parent_created=False)` | `False` |
> | `items update --attach`（metadata + attach） | `_with_attachment_context(err, parent_key=key, parent_created=False, metadata_updated=True)` | `False` |
>
> 命令层实现示例（metadata + attach 合成路径）：
>
> ```python
> def action() -> tuple[Any, dict[str, Any], Literal["success", "partial_failure"]]:
>     ...
>     # 1) metadata patch — 抛 CLIError 时直接透传，attach 没动
>     update_res = item_svc.update(...)
>
>     # 2) attach — 异常 / 全失败 都翻译成带 metadata_updated=true 的 CLIError
>     try:
>         attach_res = attach_svc.attach(parent_key=key, ...)
>     except CLIError as err:
>         raise _with_attachment_context(
>             err, parent_key=key, parent_created=False, metadata_updated=True,
>         ) from err
>
>     if attach_res.failed and not attach_res.uploaded and not attach_res.unchanged:
>         first = attach_res.failed[0]
>         err = from_code(first.code, first.message,
>                         context={"file": first.file,
>                                  "parent_item_key": first.parent_item_key,
>                                  "attachment_key": first.attachment_key,
>                                  **(first.context or {})})
>         raise _with_attachment_context(
>             err, parent_key=key, parent_created=False, metadata_updated=True,
>         )
>
>     # 部分成功 / 全成功
>     ...
> ```

### Step 5: `items create --json-file` 含多附件 → 命令层接通 `attach_many()`

> **回应 review P2（不可达代码风险）**：原版 Task 20 命令骨架只调单文件 `attach_svc.attach(...)`，`json_file` 在 typer 签名里挂着但完全没有解析，`attach_many()` 在 service 层实现完毕后会变成**不可达代码**。这违反 design §10.4（"`items create --json-file` 含多文件时 zip+prop 上传并发"）和本 plan Goal / Task 17 的明文要求。Step 5 把这条路径补回来。

**`--json-file` 输入格式**（design §6 命令树 + Phase 3 Task 6 已规定它走 `list[PyzoteroTemplate]`，Phase 4 仅扩展每条记录的可选 `_attachments`）：

```json
[
  {
    "itemType": "journalArticle",
    "title": "Paper A",
    "creators": [...],
    "_attachments": [
      {"file": "/abs/or/cwd-relative/a.pdf", "title": "Main PDF"},
      {"file": "/abs/b.pdf"}
    ]
  },
  {
    "itemType": "book",
    "title": "Book B"
  }
]
```

- `_attachments` 是**可选数组**，Phase 4 新加；缺省即"无附件"，与 Phase 3 batch create 行为兼容。
- `_attachments[].file` 必填；`_attachments[].title` 可选（缺省走文件名）。
- `_attachments` 不进 pyzotero create_items 的 payload——命令层在调 adapter 之前**剥离**它，避免污染父 item 模板。

**执行流程**（与 design §10.4 三段流水线对齐）：

```
1. 解析 JSON → list[ParentSpec]，每条 ParentSpec = (parent_payload, attachments[])
   - 同时校验所有 _attachments[].file 存在；任意一个不存在 → MUTUALLY_EXCLUSIVE_ARGS 之类的
     pre-flight 错误（这里用 FILE_NOT_FOUND，因为是用户输入级 typo）
2. parent items 串行批建：item_svc.create([parent_payloads]) — 与 Phase 3 batch create 同
   - 拿到 successful[].key + failed[]，把 successful index → 远端 key 的映射建好
3. 把 _attachments 展平成 list[AttachJob]，仅取 successful 父 item 的 attachments：
       jobs = [{"parent_key": parent_keys[i], "file_path": f, "attach_title": t}
               for i, parent_atts in enumerate(...)
               for (f, t) in parent_atts]
4. attach_svc.attach_many(jobs=jobs) — 单次命令 ≥2 文件自动启用 ThreadPoolExecutor
   - 单文件路径仍能命中此分支：attach_many 内部 len(jobs) <= 1 fallback 到 self.attach()
5. 合并结果：
   - data = {"created": [...successful parent items],
             "unchanged": [...], "failed": [...parents that failed],
             "attachments": attach_many_result.model_dump(mode="json", exclude_none=False)}
   - meta_extra.affected_keys = [...successful parent keys, ...attach_many_result.affected_keys()]
   - 全失败语义：parents 全失败（无 successful）→ 直接抛 failed[0].code 包成的 CLIError；
     attachments 全失败（uploaded[] / unchanged[] 都为空 + failed[] 非空）→ 同样抛
     failed[0]，error.context 含已成功的 parent_keys，便于 agent 续传。
   - 部分失败（任一 successful + 任一 failed）→ ok=true，audit "partial_failure"
```

**实现骨架**（命令层 helper，Task 20 Step 5 在 `commands/items.py` 加）：

```python
import json as _json
from pathlib import Path
from typing import Any, Literal

from zotero_cli.models.attachment import AttachJob
from zotero_cli.models.errors import (
    CLIError, FileNotFoundCLIError, UsageError, from_code,
)


def _parse_json_file_with_attachments(
    json_file: Path,
) -> tuple[list[dict[str, Any]], list[list[dict[str, str]]]]:
    """Return (parent_payloads_for_pyzotero, per_parent_attachment_specs).

    raise UsageError if the file isn't a JSON array of dicts (USAGE_ERROR is the
    closest registered code; we don't introduce a new error class for this single
    helper);
    raise FileNotFoundCLIError if any _attachments[].file 不存在。
    """
    try:
        raw = _json.loads(json_file.read_text())
    except _json.JSONDecodeError as exc:
        raise UsageError(f"--json-file is not valid JSON: {exc}") from exc
    if not isinstance(raw, list) or not all(isinstance(x, dict) for x in raw):
        raise UsageError("--json-file must contain a JSON array of objects.")

    parents: list[dict[str, Any]] = []
    per_parent: list[list[dict[str, str]]] = []
    for idx, entry in enumerate(raw):
        atts = entry.pop("_attachments", []) or []  # 剥离，pyzotero 不识别此字段
        if not isinstance(atts, list):
            raise UsageError(
                f"--json-file[{idx}]._attachments must be an array."
            )
        for a_idx, att in enumerate(atts):
            f = att.get("file")
            if not f:
                raise UsageError(
                    f"--json-file[{idx}]._attachments[{a_idx}].file is required."
                )
            # 早失败：任何附件文件不存在直接报错，避免父建到一半才发现
            if not Path(f).exists():
                raise FileNotFoundCLIError(
                    f"--json-file[{idx}]._attachments[{a_idx}].file not found: {f}",
                    hint="Use absolute paths or paths relative to the current working dir.",
                )
        parents.append(entry)
        per_parent.append(atts)
    return parents, per_parent


def _cmd_create_json_file_with_attachments(
    ctx: typer.Context, *, json_file: Path, dry_run: bool, options: GlobalOptions,
) -> None:
    parent_payloads, per_parent_atts = _parse_json_file_with_attachments(json_file)
    has_attachments = any(per_parent_atts)

    def dry_run_data() -> tuple[dict[str, Any], dict[str, Any]]:
        would_upload: list[dict[str, Any]] = []
        for atts in per_parent_atts:
            for a in atts:
                would_upload.append({
                    "parent_item_key": None,  # 还没建父
                    "file": a["file"],
                    "title": a.get("title", Path(a["file"]).name),
                })
        return {
            "dry_run": True,
            "would_create": parent_payloads,
            "would_upload": would_upload,
        }, {"dry_run": True, "affected_keys": []}

    def action() -> tuple[Any, dict[str, Any], Literal["success", "partial_failure"]]:
        profile = load_config(profile=options.profile, config_path=options.config_path)
        api = ZoteroAPI(profile)
        item_svc = ItemService(api)
        attach_svc = AttachmentService(profile, zotero_api=api,
                                       webdav_client=_maybe_webdav(profile),
                                       audit_log_path=None)

        # 1. parents 批建
        create_res = item_svc.create(parent_payloads)
        successful = create_res["data"]["successful"]
        failed_parents = create_res["data"]["failed"]
        unchanged_parents = create_res["data"].get("unchanged", [])

        # 全部父 item 都失败 → 抛 failed[0].code，envelope failure 退非零
        if not successful and failed_parents:
            first = failed_parents[0]
            raise from_code(first["code"], first["message"],
                            context=first.get("context") or {})

        successful_parent_keys = [s["key"] for s in successful]
        idx_to_key = {s["index"]: s["key"] for s in successful}

        # 2. 展平 attachments — 仅取 successful 父 item 的 _attachments
        jobs: list[AttachJob] = []
        for idx, atts in enumerate(per_parent_atts):
            parent_key = idx_to_key.get(idx)
            if parent_key is None:
                continue  # 父建失败的条目，跳过其 attachments
            for att in atts:
                jobs.append({
                    "parent_key": parent_key,
                    "file_path": att["file"],
                    **({"attach_title": att["title"]} if att.get("title") else {}),
                })

        # 3. attach_many — 单次命令 ≥2 文件自动启用线程池；jobs=[] 时直接构造空 result
        if jobs:
            try:
                attach_res = attach_svc.attach_many(jobs=jobs)
            except CLIError as err:
                # 父已部分建出来：把 successful_parent_keys 放进 error.context，
                # agent 可以挑选删除 / 续传。沿用 _with_attachment_context 风格但
                # 这里多个 parent，自己拼 context。
                context = {
                    **err.context,
                    "parents_created": successful_parent_keys,
                    "attachment_uploaded": False,
                    "attachment_error": {"code": err.code, "message": err.message},
                }
                raise from_code(err.code, err.message, hint=err.hint,
                                context=context, cause=err) from err
        else:
            attach_res = AttachmentResult(backend=attach_svc.backend)

        # attachments 全失败（uploaded[]/unchanged[] 都空 + failed[] 非空）→
        # 同 single-file 全失败语义：抛 failed[0].code，error.context 暴露 parent keys
        if (attach_res.failed and not attach_res.uploaded
                and not attach_res.unchanged):
            first = attach_res.failed[0]
            err = from_code(first.code, first.message,
                            context={
                                "file": first.file,
                                "parent_item_key": first.parent_item_key,
                                "attachment_key": first.attachment_key,
                                "parents_created": successful_parent_keys,
                                **(first.context or {}),
                            })
            raise err

        # 4. 合并 envelope
        data = {
            "created": successful,
            "unchanged": unchanged_parents,
            "failed": failed_parents,
            "attachments": attach_res.model_dump(mode="json", exclude_none=False),
        }
        meta_extra = {
            "backend": attach_res.backend if has_attachments else None,
            "affected_keys": [*successful_parent_keys, *attach_res.affected_keys()],
        }
        # partial_failure 触发条件：parents 有失败 OR attachments 有 per-item failure
        partial = bool(failed_parents) or bool(attach_res.failed)
        status: Literal["success", "partial_failure"] = (
            "partial_failure" if partial else "success"
        )
        return data, meta_extra, status

    _invoke_write(
        ctx, command="items.create", mode=OutputMode.SUMMARY,
        action=action,
        args_for_audit={"json_file": str(json_file)},
        dry_run=dry_run,
        dry_run_data=dry_run_data,
    )
```

> **设计 §10.4 一致性确认**：jobs 长度 ≥ 2 时 `attach_many()` 内部走三段流水线（pyzotero 串行 create / WebDAV 并发 zip+prop / pyzotero 串行 PATCH md5）。本 helper 不直接管线程池；并发策略**完全集中在 service 层**，命令层只负责入参组装与 envelope 合并。

- [ ] **Step 1:测试**(用 `runner.mix_stderr=False` 走顶层 CLI)

```python
import json
from typer.testing import CliRunner
from zotero_cli.cli import app
from zotero_cli.models.attachment import AttachmentResult, UploadedItem, FailedItem
from zotero_cli.models.errors import (
    StorageQuotaExceededError, MutuallyExclusiveArgsError,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


# ---------- items attach（独立命令）----------

def test_items_attach_subcommand_exits_zero(mocker, tmp_path, runner, tmp_profile_zfs):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    fake_result = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT", parent_item_key="P",
                     size_bytes=4, md5="h", version=1,
                     webdav_path=None, mtime_ms=None)])
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_result)
    r = runner.invoke(app, ["items", "attach", "P", str(pdf)])
    assert r.exit_code == 0
    assert "ATT" in r.stdout
    assert r.stderr == ""


def test_items_attach_quiet_outputs_only_attachment_key(mocker, tmp_path, runner, tmp_profile_zfs):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    fake_result = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT", parent_item_key="P",
                     size_bytes=4, md5="h", version=1,
                     webdav_path=None, mtime_ms=None)])
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_result)
    r = runner.invoke(app, ["--quiet", "items", "attach", "P", str(pdf)])
    assert r.exit_code == 0
    assert r.stdout == "ATT\n"


def test_items_attach_json_envelope_data_has_null_fields_for_zfs(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """设计 §8.3 字段总存在原则:webdav_path / mtime_ms 在 ZFS 后端必须输出 null,不省略"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    fake_result = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT", parent_item_key="P",
                     size_bytes=4, md5="h", version=1,
                     webdav_path=None, mtime_ms=None)])
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_result)
    r = runner.invoke(app, ["--json", "items", "attach", "P", str(pdf)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    upload = parsed["data"]["uploaded"][0]
    assert "webdav_path" in upload and upload["webdav_path"] is None
    assert "mtime_ms" in upload and upload["mtime_ms"] is None


def test_items_attach_force_zfs_exits_64_via_real_flag(mocker, tmp_path, runner,
                                                       tmp_profile_zfs):
    """ZFS 后端 + --force → MutuallyExclusiveArgsError, 默认模式错误走 stderr (设计 §10.0.2.3)"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    # AttachmentService.attach 内 precheck 阶段抛 MutuallyExclusiveArgsError
    spy = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach",
        side_effect=MutuallyExclusiveArgsError(
            "--force is only supported with WebDAV backend",
            hint="...",
        ),
    )
    r = runner.invoke(app, ["items", "attach", "P", str(pdf),
                            "--reuse-key", "ATT", "--force"])
    assert r.exit_code == 64
    assert r.stdout == ""                                # 默认模式 stdout 必空
    assert "MUTUALLY_EXCLUSIVE_ARGS" in r.stderr         # 错误走 stderr


def test_items_attach_json_quiet_mutex_rejected_before_service(mocker, runner,
                                                               tmp_profile_zfs, tmp_path):
    """全局 --json + --quiet → run_command 第一步就拒绝,service.attach 0 calls"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    spy = mocker.patch("zotero_cli.commands.items.AttachmentService.attach")
    r = runner.invoke(app, ["--json", "--quiet", "items", "attach", "P", str(pdf)])
    assert r.exit_code == 64
    parsed = json.loads(r.stdout)                        # json 模式错误走 stdout
    assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"
    assert spy.call_count == 0


def test_items_attach_writes_audit_log_on_success(mocker, tmp_path, runner, tmp_profile_zfs):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    fake_result = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT", parent_item_key="P",
                     size_bytes=4, md5="h", version=1,
                     webdav_path=None, mtime_ms=None)])
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_result)
    runner.invoke(app, ["items", "attach", "P", str(pdf)])
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["command"] == "items.attach"
    assert entry["result"] == "success"
    assert entry["affected_keys"] == ["ATT"]


def test_items_attach_writes_audit_log_on_partial_failure(mocker, tmp_path, runner,
                                                          tmp_profile_zfs):
    """attach 完成,uploaded 非空 + failed 非空 → audit result='partial_failure',exit 0。

    回应 review P1：'全失败'(uploaded[]/unchanged[] 均空 + failed[] 非空)走 failure
    路径退非零(见 test_items_attach_total_failure_exits_nonzero);仅当 uploaded 或
    unchanged 至少一项非空时才是部分失败、envelope ok=true、audit='partial_failure'。
    单文件 attach 不可能产生这种状态，但 items create --json-file 多附件路径会(Task 17/A4)。
    本测试用 service 层多文件 happy + per-item failure 来覆盖。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    fake_result = AttachmentResult(
        backend="zfs",
        uploaded=[UploadedItem(file="p.pdf", attachment_key="ATT_OK",
                               parent_item_key="P", size_bytes=4, md5="h", version=1,
                               webdav_path=None, mtime_ms=None)],
        unchanged=[],
        failed=[FailedItem(file="other.pdf", attachment_key=None, parent_item_key="P",
                           code="INVALID_FILE", message="Bad PDF",
                           context={"size_bytes": 4})],
    )
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_result)
    r = runner.invoke(app, ["items", "attach", "P", str(pdf)])
    assert r.exit_code == 0                              # 部分失败仍退 0
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "partial_failure"
    assert entry["affected_keys"] == ["ATT_OK"]          # uploaded 进 affected_keys


def test_items_attach_total_failure_exits_nonzero(mocker, tmp_path, runner,
                                                  tmp_profile_zfs):
    """attach 完成,但 uploaded[]/unchanged[] 均空 + failed[] 非空 → 走 envelope failure
    路径,退码沿 failed[0].code 映射(此处 INVALID_FILE → user_error=1)。

    回应 review P1：design §10.0.2.5 B2 / C 要求"全失败退 2，部分失败退 0(success 非空时)"。
    具体退码取决于 failed[0].code 在 §9.x 错误码映射表里的退出类别——这里 INVALID_FILE
    属 user_error → 1；STORAGE_QUOTA_EXCEEDED → network_error → 2。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    fake_result = AttachmentResult(
        backend="zfs",
        uploaded=[],
        unchanged=[],
        failed=[FailedItem(file="p.pdf", attachment_key=None, parent_item_key="P",
                           code="INVALID_FILE", message="Bad PDF",
                           context={"size_bytes": 4})],
    )
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_result)
    r = runner.invoke(app, ["--json", "items", "attach", "P", str(pdf)])
    assert r.exit_code == 1                              # INVALID_FILE → user_error
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "INVALID_FILE"
    assert parsed["error"]["context"]["parent_item_key"] == "P"
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "failure"                  # _invoke_write 写 failure
    assert entry["error_code"] == "INVALID_FILE"


def test_items_attach_writes_audit_log_on_adapter_failure(mocker, tmp_path, runner,
                                                          tmp_profile_zfs):
    """adapter 抛 CLIError → _invoke_write 写 result='failure'"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 side_effect=StorageQuotaExceededError("over"))
    r = runner.invoke(app, ["items", "attach", "P", str(pdf)])
    assert r.exit_code == 2                              # network_error
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "failure"
    assert entry["error_code"] == "STORAGE_QUOTA_EXCEEDED"


def test_items_attach_dry_run_returns_would_upload_without_service_call(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    spy = mocker.patch("zotero_cli.commands.items.AttachmentService.attach")
    r = runner.invoke(app, ["--json", "items", "attach", "P", str(pdf), "--dry-run"])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["data"]["dry_run"] is True
    assert parsed["data"]["would_upload"] == [{
        "parent_item_key": "P", "file": str(pdf), "title": "p.pdf",
        "reuse_key": None, "force": False,
    }]
    assert parsed["meta"]["dry_run"] is True
    assert parsed["meta"]["affected_keys"] == []
    assert spy.call_count == 0


# ---------- items create --attach(error.context partial state)----------

def test_items_create_with_attach_full_success(mocker, tmp_path, runner, tmp_profile_zfs):
    """全成功:envelope ok=true, data 含 parent_item_key + attachment 信息"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    mocker.patch("zotero_cli.commands.items.ItemService.create_single",
                 return_value={"index": 0, "key": "P_NEW", "version": 1, "data": {}})
    fake_attach = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT_NEW", parent_item_key="P_NEW",
                     size_bytes=4, md5="h", version=2,
                     webdav_path=None, mtime_ms=None)])
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "create",
                            "--type", "journalArticle", "--title", "T",
                            "--attach", str(pdf)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is True
    assert parsed["data"]["parent_created"] is True
    assert parsed["data"]["parent_item_key"] == "P_NEW"
    assert parsed["data"]["attachment_uploaded"] is True
    assert parsed["meta"]["affected_keys"] == ["P_NEW", "ATT_NEW"]


def test_items_create_with_attach_a2_context_on_attach_exception(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """A2: 父建成功 + attach 抛 CLIError → data=null, parent key 在 error.context"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    mocker.patch("zotero_cli.commands.items.ItemService.create_single",
                 return_value={"index": 0, "key": "P_NEW", "version": 1, "data": {}})
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 side_effect=StorageQuotaExceededError("over quota"))
    r = runner.invoke(app, ["--json", "items", "create",
                            "--type", "journalArticle", "--title", "T",
                            "--attach", str(pdf)])
    assert r.exit_code == 2
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "STORAGE_QUOTA_EXCEEDED"
    ctx = parsed["error"]["context"]
    assert ctx["parent_created"] is True
    assert ctx["parent_item_key"] == "P_NEW"
    assert ctx["attachment_uploaded"] is False
    assert ctx["attachment_error"]["code"] == "STORAGE_QUOTA_EXCEEDED"


def test_items_create_with_attach_a3_total_failure_exits_nonzero(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """A3: 父建成功 + attach 完成但 failed[] 非空 + uploaded[]/unchanged[] 均空 → 全失败,
    走 envelope failure 路径退非零(沿 failed[0].code 映射),audit='failure'。

    回应 review P1：design §10.0.2.5 B2 / C 要求"全失败退 2(失败码映射),部分失败退 0"。
    父 item 已创建这一信息通过 error.context.parent_created=true / parent_item_key
    暴露给 agent；不靠"退 0 + ok=true"传达。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    mocker.patch("zotero_cli.commands.items.ItemService.create_single",
                 return_value={"index": 0, "key": "P_NEW", "version": 1, "data": {}})
    fake_attach = AttachmentResult(
        backend="zfs", uploaded=[], unchanged=[],
        failed=[FailedItem(file="p.pdf", attachment_key=None, parent_item_key="P_NEW",
                           code="INVALID_FILE", message="Bad PDF", context=None)],
    )
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "create",
                            "--type", "journalArticle", "--title", "T",
                            "--attach", str(pdf)])
    assert r.exit_code == 1                              # INVALID_FILE → user_error
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None                        # envelope failure invariant
    assert parsed["error"]["code"] == "INVALID_FILE"
    ctx = parsed["error"]["context"]
    assert ctx["parent_created"] is True                 # 父已建出来
    assert ctx["parent_item_key"] == "P_NEW"
    assert ctx["attachment_uploaded"] is False
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "failure"                  # 不是 partial_failure
    assert entry["error_code"] == "INVALID_FILE"


def test_items_create_with_attach_a4_partial_success_uploaded_and_failed(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """A4: 父建成功 + uploaded[] 非空 + failed[] 也非空(多附件 partial success)→
    envelope ok=true,exit 0,audit='partial_failure'。

    单文件 items create --attach 不会进入此分支(Task 12 中间态不存在),但 multi-file
    create --json-file 路径会;为锁住 schema 此处用 service 层 fake。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    mocker.patch("zotero_cli.commands.items.ItemService.create_single",
                 return_value={"index": 0, "key": "P_NEW", "version": 1, "data": {}})
    fake_attach = AttachmentResult(
        backend="zfs",
        uploaded=[UploadedItem(file="ok.pdf", attachment_key="ATT_OK",
                               parent_item_key="P_NEW", size_bytes=4, md5="h",
                               version=2, webdav_path=None, mtime_ms=None)],
        unchanged=[],
        failed=[FailedItem(file="bad.pdf", attachment_key=None,
                           parent_item_key="P_NEW",
                           code="INVALID_FILE", message="Bad PDF", context=None)],
    )
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "create",
                            "--type", "journalArticle", "--title", "T",
                            "--attach", str(pdf)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is True
    assert parsed["data"]["parent_created"] is True
    assert parsed["data"]["parent_item_key"] == "P_NEW"
    assert parsed["data"]["attachment_uploaded"] is True
    assert len(parsed["data"]["uploaded"]) == 1
    assert len(parsed["data"]["failed"]) == 1
    assert parsed["meta"]["affected_keys"] == ["P_NEW", "ATT_OK"]
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "partial_failure"


def test_items_create_with_attach_a1_parent_create_fails_no_partial(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """A1: 父建本身失败 → 标准 failure 路径,data 为 null(没有 parent_item_key)"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    from zotero_cli.models.errors import ApiTimeoutError
    mocker.patch("zotero_cli.commands.items.ItemService.create_single",
                 side_effect=ApiTimeoutError("timeout"))
    spy_attach = mocker.patch("zotero_cli.commands.items.AttachmentService.attach")
    r = runner.invoke(app, ["--json", "items", "create",
                            "--type", "journalArticle", "--title", "T",
                            "--attach", str(pdf)])
    assert r.exit_code == 2
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None                        # 父没建出来,data 必须 null
    assert spy_attach.call_count == 0                    # attach 没被调


def test_items_create_with_attach_dry_run_has_would_create_and_would_upload(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    spy_create = mocker.patch("zotero_cli.commands.items.ItemService.create_single")
    spy_attach = mocker.patch("zotero_cli.commands.items.AttachmentService.attach")
    r = runner.invoke(app, ["--json", "items", "create",
                            "--type", "journalArticle", "--title", "T",
                            "--attach", str(pdf), "--dry-run"])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["data"]["dry_run"] is True
    assert parsed["data"]["would_create"][0]["itemType"] == "journalArticle"
    assert parsed["data"]["would_create"][0]["title"] == "T"
    assert parsed["data"]["would_upload"] == [{
        "parent_item_key": None, "file": str(pdf), "title": "p.pdf",
    }]
    assert parsed["meta"]["affected_keys"] == []
    assert spy_create.call_count == 0
    assert spy_attach.call_count == 0


# ---------- items update --attach ----------

def test_items_update_with_attach_only_success(mocker, tmp_path, runner, tmp_profile_zfs):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    spy_update = mocker.patch("zotero_cli.commands.items.ItemService.update")
    fake_attach = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT_NEW", parent_item_key="P",
                     size_bytes=4, md5="h", version=2,
                     webdav_path=None, mtime_ms=None)])
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "update", "P", "--attach", str(pdf)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["data"]["parent_item_key"] == "P"
    assert parsed["data"]["attachment_uploaded"] is True
    assert parsed["meta"]["affected_keys"] == ["ATT_NEW"]
    assert spy_update.call_count == 0


def test_items_update_metadata_and_attach_success(mocker, tmp_path, runner, tmp_profile_zfs):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    mocker.patch("zotero_cli.commands.items.ItemService.update",
                 return_value={"data": {"successful": [{"index": 0, "key": "P", "version": 3}],
                                        "unchanged": [], "failed": []},
                               "meta_extra": {"affected_keys": ["P"]}})
    fake_attach = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file="p.pdf", attachment_key="ATT_NEW", parent_item_key="P",
                     size_bytes=4, md5="h", version=2,
                     webdav_path=None, mtime_ms=None)])
    attach_spy = mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                              return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "update", "P",
                            "--title", "Parent Title",
                            "--attach", str(pdf), "--attach-title", "Attachment Title"])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["data"]["metadata_updated"] is True
    assert parsed["data"]["parent_item_key"] == "P"
    assert parsed["meta"]["affected_keys"] == ["P", "ATT_NEW"]
    assert attach_spy.call_args.kwargs["attach_title"] == "Attachment Title"


def test_items_update_metadata_then_attach_failure_context(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    mocker.patch("zotero_cli.commands.items.ItemService.update",
                 return_value={"data": {"successful": [{"index": 0, "key": "P", "version": 3}],
                                        "unchanged": [], "failed": []},
                               "meta_extra": {"affected_keys": ["P"]}})
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 side_effect=StorageQuotaExceededError("over quota"))
    r = runner.invoke(app, ["--json", "items", "update", "P",
                            "--title", "Parent Title", "--attach", str(pdf)])
    assert r.exit_code == 2
    parsed = json.loads(r.stdout)
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "STORAGE_QUOTA_EXCEEDED"
    ctx = parsed["error"]["context"]
    assert ctx["parent_item_key"] == "P"
    assert ctx["metadata_updated"] is True
    assert ctx["attachment_uploaded"] is False
    # 回应 review P1：父 item 是既有 item，不是本次新建——不能让 agent 误删
    assert ctx["parent_created"] is False


def test_items_update_attach_only_failure_does_not_set_parent_created(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """`items update <key> --attach <file>`（无 metadata flag）attach 失败时，
    error.context 必须 `parent_created=false`——P 是用户传入的既有 key，绝不能
    被 agent 当作"本次新建可回滚"对象删除。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    spy_update = mocker.patch("zotero_cli.commands.items.ItemService.update")
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 side_effect=StorageQuotaExceededError("over quota"))
    r = runner.invoke(app, ["--json", "items", "update", "P", "--attach", str(pdf)])
    assert r.exit_code == 2
    parsed = json.loads(r.stdout)
    assert parsed["data"] is None
    ctx = parsed["error"]["context"]
    assert ctx["parent_item_key"] == "P"
    assert ctx["parent_created"] is False
    assert ctx["attachment_uploaded"] is False
    # 没带 metadata flag → metadata_updated 不应出现，或为 None / False
    assert ctx.get("metadata_updated") in (None, False)
    spy_update.assert_not_called()


def test_items_update_with_attach_total_failure_exits_nonzero(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """`items update --attach` attach 完成但全失败（uploaded[]/unchanged[] 均空 +
    failed[] 非空）→ envelope failure，退码沿 failed[0].code 映射（INVALID_FILE → 1）。

    回应 review P1：design §10.0.2.5 B2 "全失败退 2，部分失败退 0(success 非空时)"。
    parent_created 必须 false（既有 item，不能让 agent 误删）。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    fake_attach = AttachmentResult(
        backend="zfs", uploaded=[], unchanged=[],
        failed=[FailedItem(file="p.pdf", attachment_key=None, parent_item_key="P",
                           code="INVALID_FILE", message="Bad PDF", context=None)],
    )
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "update", "P", "--attach", str(pdf)])
    assert r.exit_code == 1                              # INVALID_FILE → user_error
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "INVALID_FILE"
    ctx = parsed["error"]["context"]
    assert ctx["parent_item_key"] == "P"
    assert ctx["parent_created"] is False
    assert ctx["attachment_uploaded"] is False
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "failure"
    assert entry["error_code"] == "INVALID_FILE"


def test_items_update_metadata_then_attach_total_failure_exits_nonzero(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """metadata patch 成功 + attach 全失败 → envelope failure 退非零，
    error.context.metadata_updated=true，parent_created=false。"""
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    mocker.patch("zotero_cli.commands.items.ItemService.update",
                 return_value={"data": {"successful": [{"index": 0, "key": "P", "version": 3}],
                                        "unchanged": [], "failed": []},
                               "meta_extra": {"affected_keys": ["P"]}})
    fake_attach = AttachmentResult(
        backend="zfs", uploaded=[], unchanged=[],
        failed=[FailedItem(file="p.pdf", attachment_key=None, parent_item_key="P",
                           code="INVALID_FILE", message="Bad PDF", context=None)],
    )
    mocker.patch("zotero_cli.commands.items.AttachmentService.attach",
                 return_value=fake_attach)
    r = runner.invoke(app, ["--json", "items", "update", "P",
                            "--title", "Parent Title", "--attach", str(pdf)])
    assert r.exit_code == 1                              # INVALID_FILE → user_error
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "INVALID_FILE"
    ctx = parsed["error"]["context"]
    assert ctx["metadata_updated"] is True
    assert ctx["parent_created"] is False
    assert ctx["attachment_uploaded"] is False


def test_items_update_with_attach_dry_run_has_would_update_and_would_upload(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF")
    spy_update = mocker.patch("zotero_cli.commands.items.ItemService.update")
    spy_attach = mocker.patch("zotero_cli.commands.items.AttachmentService.attach")
    r = runner.invoke(app, ["--json", "items", "update", "P",
                            "--title", "Parent Title",
                            "--attach", str(pdf), "--dry-run"])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["data"]["dry_run"] is True
    assert parsed["data"]["would_update"] == [{"key": "P", "patch": {"title": "Parent Title"}}]
    assert parsed["data"]["would_upload"] == [{
        "parent_item_key": "P", "file": str(pdf), "title": "p.pdf",
    }]
    assert parsed["meta"]["affected_keys"] == []
    assert spy_update.call_count == 0
    assert spy_attach.call_count == 0


# ---------- items create --json-file 多附件路径（review P2）----------

def _write_json_file(path, entries):
    path.write_text(json.dumps(entries))
    return path


def test_items_create_json_file_multi_parents_with_attachments_calls_attach_many(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """≥2 个附件 → 命令层应调 AttachmentService.attach_many（而不是 .attach）。
    回应 review P2：避免 attach_many 实现成不可达代码。"""
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "Paper A",
         "_attachments": [{"file": str(pdf1), "title": "Main"},
                          {"file": str(pdf2)}]},
        {"itemType": "book", "title": "Book B"},
    ])
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {
                "successful": [
                    {"index": 0, "key": "P_A", "version": 1, "data": {}},
                    {"index": 1, "key": "P_B", "version": 1, "data": {}},
                ],
                "unchanged": [],
                "failed": [],
            },
            "meta_extra": {"affected_keys": ["P_A", "P_B"]},
        },
    )
    fake_attach = AttachmentResult(
        backend="zfs",
        uploaded=[
            UploadedItem(file=str(pdf1), attachment_key="ATT1",
                         parent_item_key="P_A", size_bytes=5, md5="ha", version=1,
                         webdav_path=None, mtime_ms=None),
            UploadedItem(file=str(pdf2), attachment_key="ATT2",
                         parent_item_key="P_A", size_bytes=5, md5="hb", version=1,
                         webdav_path=None, mtime_ms=None),
        ],
    )
    spy_attach = mocker.patch("zotero_cli.commands.items.AttachmentService.attach")
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many",
        return_value=fake_attach,
    )

    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is True
    # attach_many 必须被调用一次；attach 单文件入口不应进
    assert spy_attach_many.call_count == 1
    assert spy_attach.call_count == 0
    # jobs 顺序：仅来自 successful 父 item，且按 _attachments 顺序展平
    jobs = spy_attach_many.call_args.kwargs["jobs"]
    assert [j["parent_key"] for j in jobs] == ["P_A", "P_A"]
    assert [j["file_path"] for j in jobs] == [str(pdf1), str(pdf2)]
    assert jobs[0]["attach_title"] == "Main"
    assert "attach_title" not in jobs[1]
    # envelope.data + meta 合并
    assert {x["key"] for x in parsed["data"]["created"]} == {"P_A", "P_B"}
    assert {u["attachment_key"] for u in parsed["data"]["attachments"]["uploaded"]} \
        == {"ATT1", "ATT2"}
    assert parsed["meta"]["affected_keys"] == ["P_A", "P_B", "ATT1", "ATT2"]


def test_items_create_json_file_single_attachment_falls_back_to_serial(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """单个 _attachments 仍走 attach_many（service 层内部 fallback 到 self.attach）；
    命令层不再分流——保持单一入口，不让分支逻辑漏写到命令层。"""
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"%PDF")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "T",
         "_attachments": [{"file": str(pdf)}]},
    ])
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {"successful": [{"index": 0, "key": "P", "version": 1, "data": {}}],
                     "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": ["P"]},
        },
    )
    fake_attach = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file=str(pdf), attachment_key="ATT", parent_item_key="P",
                     size_bytes=4, md5="h", version=1,
                     webdav_path=None, mtime_ms=None)])
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many",
        return_value=fake_attach,
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 0
    assert spy_attach_many.call_count == 1
    assert len(spy_attach_many.call_args.kwargs["jobs"]) == 1


def test_items_create_json_file_no_attachments_skips_attach_many(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """所有条目都没 _attachments → attach_many 不应被调；envelope.data.attachments 仍是
    空 AttachmentResult 序列化（schema 完整）。"""
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "Only metadata"},
    ])
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {"successful": [{"index": 0, "key": "P", "version": 1, "data": {}}],
                     "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": ["P"]},
        },
    )
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many"
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert spy_attach_many.call_count == 0
    assert parsed["data"]["attachments"]["uploaded"] == []
    assert parsed["data"]["attachments"]["failed"] == []
    assert parsed["meta"]["affected_keys"] == ["P"]


def test_items_create_json_file_skips_attachments_for_failed_parents(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """parent index 1 创建失败 → 它的 _attachments 不进 jobs；index 0 的进。"""
    pdf_a = tmp_path / "a.pdf"; pdf_a.write_bytes(b"%PDFa")
    pdf_b = tmp_path / "b.pdf"; pdf_b.write_bytes(b"%PDFb")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "OK",
         "_attachments": [{"file": str(pdf_a)}]},
        {"itemType": "bogusType", "title": "Bad",
         "_attachments": [{"file": str(pdf_b)}]},
    ])
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {
                "successful": [{"index": 0, "key": "P_OK", "version": 1, "data": {}}],
                "unchanged": [],
                "failed": [{"index": 1, "code": "INVALID_ITEM_TYPE",
                            "message": "bogusType not a valid type",
                            "context": {"item_type": "bogusType"}}],
            },
            "meta_extra": {"affected_keys": ["P_OK"]},
        },
    )
    fake_attach = AttachmentResult(backend="zfs", uploaded=[
        UploadedItem(file=str(pdf_a), attachment_key="ATT_A", parent_item_key="P_OK",
                     size_bytes=5, md5="ha", version=1,
                     webdav_path=None, mtime_ms=None)])
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many",
        return_value=fake_attach,
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 0                              # parent 部分失败 → ok=true
    parsed = json.loads(r.stdout)
    jobs = spy_attach_many.call_args.kwargs["jobs"]
    assert len(jobs) == 1                                # 仅 P_OK 的附件
    assert jobs[0]["parent_key"] == "P_OK"
    assert jobs[0]["file_path"] == str(pdf_a)
    assert parsed["data"]["failed"][0]["code"] == "INVALID_ITEM_TYPE"
    assert parsed["meta"]["affected_keys"] == ["P_OK", "ATT_A"]


def test_items_create_json_file_all_parents_failed_exits_nonzero(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """所有父 item 都失败 → envelope failure 退非零；attach_many 不被调。"""
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"%PDF")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "bogus", "title": "X",
         "_attachments": [{"file": str(pdf)}]},
    ])
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {
                "successful": [],
                "unchanged": [],
                "failed": [{"index": 0, "code": "INVALID_ITEM_TYPE",
                            "message": "bogus not a valid type", "context": {}}],
            },
            "meta_extra": {"affected_keys": []},
        },
    )
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many"
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 1                              # INVALID_ITEM_TYPE → user_error
    assert spy_attach_many.call_count == 0
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None


def test_items_create_json_file_attach_many_total_failure_exits_nonzero(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """父全建成功，但 attach_many 全失败（uploaded[]/unchanged[] 均空）→ 退非零；
    error.context.parents_created 暴露已建父 key 给 agent 做后续修复。"""
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "T",
         "_attachments": [{"file": str(pdf1)}, {"file": str(pdf2)}]},
    ])
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {"successful": [{"index": 0, "key": "P", "version": 1, "data": {}}],
                     "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": ["P"]},
        },
    )
    fake_attach = AttachmentResult(
        backend="zfs", uploaded=[], unchanged=[],
        failed=[
            FailedItem(file=str(pdf1), attachment_key=None, parent_item_key="P",
                       code="INVALID_FILE", message="Bad", context=None),
            FailedItem(file=str(pdf2), attachment_key=None, parent_item_key="P",
                       code="INVALID_FILE", message="Bad", context=None),
        ],
    )
    mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many",
        return_value=fake_attach,
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 1                              # INVALID_FILE → user_error
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is False
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "INVALID_FILE"
    assert parsed["error"]["context"]["parents_created"] == ["P"]


def test_items_create_json_file_partial_attach_failure_exits_zero(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """父全建成功 + attach 部分成功 → ok=true,exit 0,audit='partial_failure'。"""
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "T",
         "_attachments": [{"file": str(pdf1)}, {"file": str(pdf2)}]},
    ])
    audit = tmp_path / "audit.log"
    mocker.patch("zotero_cli.commands.items.audit_log_path", return_value=audit)
    mocker.patch(
        "zotero_cli.commands.items.ItemService.create",
        return_value={
            "data": {"successful": [{"index": 0, "key": "P", "version": 1, "data": {}}],
                     "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": ["P"]},
        },
    )
    fake_attach = AttachmentResult(
        backend="zfs",
        uploaded=[UploadedItem(file=str(pdf1), attachment_key="ATT_OK",
                               parent_item_key="P", size_bytes=5, md5="ha", version=1,
                               webdav_path=None, mtime_ms=None)],
        unchanged=[],
        failed=[FailedItem(file=str(pdf2), attachment_key=None, parent_item_key="P",
                           code="INVALID_FILE", message="Bad", context=None)],
    )
    mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many",
        return_value=fake_attach,
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["ok"] is True
    assert {u["attachment_key"] for u in parsed["data"]["attachments"]["uploaded"]} \
        == {"ATT_OK"}
    assert len(parsed["data"]["attachments"]["failed"]) == 1
    assert parsed["meta"]["affected_keys"] == ["P", "ATT_OK"]
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["result"] == "partial_failure"


def test_items_create_json_file_with_attach_flag_is_mutually_exclusive(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """`--json-file` 与 `--attach` 互斥（design §6 + Phase 4 P2 防御）。"""
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"%PDF")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "T"}
    ])
    spy_create = mocker.patch("zotero_cli.commands.items.ItemService.create")
    r = runner.invoke(app, ["--json", "items", "create",
                            "--json-file", str(json_file), "--attach", str(pdf)])
    assert r.exit_code == 64                             # MUTUALLY_EXCLUSIVE_ARGS
    parsed = json.loads(r.stdout)
    assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"
    assert spy_create.call_count == 0


def test_items_create_json_file_local_attachment_missing_aborts_before_create(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    """JSON 列出的本地 attachment 文件不存在 → pre-flight FILE_NOT_FOUND，
    parents 还没建。回应 review P2：避免父建到一半才发现路径错。"""
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "T",
         "_attachments": [{"file": str(tmp_path / "missing.pdf")}]},
    ])
    spy_create = mocker.patch("zotero_cli.commands.items.ItemService.create")
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many"
    )
    r = runner.invoke(app, ["--json", "items", "create", "--json-file", str(json_file)])
    assert r.exit_code == 1                              # FILE_NOT_FOUND → user_error
    parsed = json.loads(r.stdout)
    assert parsed["error"]["code"] == "FILE_NOT_FOUND"
    assert spy_create.call_count == 0
    assert spy_attach_many.call_count == 0


def test_items_create_json_file_dry_run_lists_would_upload_and_no_service_calls(
    mocker, tmp_path, runner, tmp_profile_zfs,
):
    pdf1 = tmp_path / "a.pdf"; pdf1.write_bytes(b"%PDFa")
    pdf2 = tmp_path / "b.pdf"; pdf2.write_bytes(b"%PDFb")
    json_file = _write_json_file(tmp_path / "in.json", [
        {"itemType": "journalArticle", "title": "T",
         "_attachments": [{"file": str(pdf1), "title": "Main"},
                          {"file": str(pdf2)}]},
    ])
    spy_create = mocker.patch("zotero_cli.commands.items.ItemService.create")
    spy_attach_many = mocker.patch(
        "zotero_cli.commands.items.AttachmentService.attach_many"
    )
    r = runner.invoke(app, ["--json", "items", "create",
                            "--json-file", str(json_file), "--dry-run"])
    assert r.exit_code == 0
    parsed = json.loads(r.stdout)
    assert parsed["data"]["dry_run"] is True
    assert parsed["data"]["would_create"] == [{
        "itemType": "journalArticle", "title": "T",  # _attachments 已剥离
    }]
    assert parsed["data"]["would_upload"] == [
        {"parent_item_key": None, "file": str(pdf1), "title": "Main"},
        {"parent_item_key": None, "file": str(pdf2), "title": "b.pdf"},
    ]
    assert spy_create.call_count == 0
    assert spy_attach_many.call_count == 0
```

- [ ] **Step 2: 实现** — 按上文 Step 1 / Step 2 / Step 3 / Step 4 / Step 5 顺序在 `commands/items.py` 加 typer 选项与子命令，boilerplate 与 Phase 3 既有 `items create` / `items update` 风格一致；A2 / metadata+attach 失败通过 `error.context` 暴露 partial state，不改 `Envelope.failure(...)`；Step 5 把 `--json-file` 多附件路径接到 `attach_many()`，避免 service 实现成不可达代码（review P2）

- [ ] **Step 3**:测 + commit `feat(items): add attachment command paths with dry-run, partial-state context, and json-file multi-attachment dispatch`

---

## Task 21: 手动测试清单执行

**Files:** `DEVELOPMENT.md`(记录结果)

跑设计 §12.5 + DEVELOPMENT.md §9.4 中所有附件相关项,记录通过/失败。需要真实账号(personal 与 group 各一个)+ 一台 WebDAV server。

- [ ] **Step 1**:准备测试环境 — 临时账号 / WebDAV(自建 nginx-dav 或 Box.com)

- [ ] **Step 2**:逐项跑 §12.5 表中标 ZFS 后端 / WebDAV 后端 / 后端切换 / group library 拒绝 / `--attach-title` 不污染 / `items attach --title` / `--reuse-key` ZFS / `--reuse-key` WebDAV / `--reuse-key` 不存在 key / ZFS `--force` 拒绝 / WebDAV `--force` / `--quiet` unchanged / mtime 一致性 / base64 编码 / 大文件 100MB(可选,确认不 OOM)

- [ ] **Step 3**:每项记录到 `DEVELOPMENT.md §9.4` 后或一个临时 manual-test-log.md(如不入库,本地记后丢弃),失败项回到对应 Task 修复

- [ ] **Step 4**:全部通过后 commit `docs: record phase 4 manual test results`(若 DEVELOPMENT.md 有改动)

---

## Task 22: 阶段 4 验收 tick + 覆盖率

**Files:** `DEVELOPMENT.md`

- [ ] **Step 1**:跑完整自检
  ```bash
  uv run ruff check src tests
  uv run ruff format --check src tests
  uv run mypy src
  uv run pytest --cov=src/zotero_cli --cov-report=term-missing
  ```

- [ ] **Step 2**:验证设计 §12.4 覆盖率目标
  | 模块 | 目标 | 实测 |
  |---|---|---|
  | `adapters/webdav_client.py` | 95%+ | ____ |
  | `services/attachment_service.py` | 85%+ | ____ |
  | `adapters/zotero_api.py`(扩展部分)| 85%+ | ____ |
  | `commands/items.py`(attach 部分)| 70%+ | ____ |
  | 总体 | 85%+ | ____ |

- [ ] **Step 3**:把 DEVELOPMENT.md §9.4 每条 `[ ]` 改成 `[x]`(本身没改的留 `[ ]` 并说明)

- [ ] **Step 4**:commit
  ```bash
  git add DEVELOPMENT.md
  git commit -m "docs: tick phase 4 acceptance checklist"
  ```

阶段 4 完成。下一步进入阶段 5(RSS / SQLite),见 `2026-06-07-phase-5-rss.md`。

---

## 自检清单(全阶段汇总)

每次 PR / 合并前:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src/zotero_cli --cov-report=term-missing
```

四项全过 + 当前 task 的覆盖率达标才能 commit / merge。

WebDAV 协议字节级一致性额外要求:`tests/fixtures/sample_prop.xml` 与 `build_prop` 输出 `bytes-equal` 测试必过(Task 4)。

---

## 阶段验收 checklist

参见 `DEVELOPMENT.md §9.4`(阶段 4)。



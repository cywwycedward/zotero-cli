# 阶段 4 待解决问题调研报告

**日期**：2026-06-08
**涉及文件**：`adapters/webdav_client.py`、`services/attachment_service.py`
**参考实现**：[54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) — `src/zotero_mcp/webdav.py`

---

## 问题 1：WebDAV 协议格式未经验证

### 背景

设计文档 §10.1 明确声明："以下协议描述基于源码逆向 + 社区文档整理，**不是 Zotero 官方公开规范**。实施前必须按 §10.6 风险点逐项实测验证"。当前 `webdav_client.py` 的实现完全基于设计文档假设，未做实测。

以下对比我们的实现与 zotero-mcp 参考实现，逐项分析每个协议细节。

---

### 1.1 ZIP 内部文件名编码方案

| 维度 | 我们的实现 | zotero-mcp |
|---|---|---|
| 编码方式 | **标准 base64** (`base64.b64encode(name.encode('utf-8'))`) | **无编码**（直接用 `src.name` 原始文件名） |
| 示例 | `test.pdf` → `dGVzdC5wZGY=` | `test.pdf` → `test.pdf` |
| 非 ASCII | base64 编码后变为纯 ASCII | Python zipfile 默认设置 UTF-8 flag |
| 代码位置 | `webdav_client.py:33-34` | `zotero_mcp/webdav.py: _build_zotero_zip()` |

**关键差异**：这是**最严重的协议不兼容**。如果 Zotero 桌面端期望 zip 内部文件名是原始名称，我们的 base64 编码会导致桌面端无法正确解压和识别附件。

**zotero-mcp 代码**：
```python
def _build_zotero_zip(file_path: str | Path) -> bytes:
    src = Path(file_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src, arcname=src.name)
    return buf.getvalue()
```

**我们的代码**：
```python
def _build_zip(file_path: Path) -> bytes:
    raw_name = file_path.name.encode("utf-8")
    internal_name = base64.b64encode(raw_name).decode("ascii")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(internal_name, file_path.read_bytes())
    return buf.getvalue()
```

**结论**：设计 §10.1 说"文件名是原始文件名的 base64 编码"，但 zotero-mcp 实测不做 base64。**需要用 Zotero 桌面端实际上传一个 PDF，下载 `.zip` 验证内部文件名格式**才能确定真相。在此之前按照 zotero-mcp 的做法（不编码）是更安全的选择——因为它是一个已被验证可用的实现。

**待确认行动**：
- [ ] 配置 Zotero 桌面端 + WebDAV 后端，上传一个 PDF
- [ ] 从 WebDAV 服务器下载 `.zip`，用 `zipfile.ZipFile.namelist()` 检查内部文件名
- [ ] 如果内部文件名是原始名（非 base64），修改 `_build_zip` 并更新设计文档 §10.1

---

### 1.2 压缩级别

| 维度 | 我们的实现 | zotero-mcp |
|---|---|---|
| compress_type | `ZIP_STORED` (0) — 不压缩 | `ZIP_DEFLATED` — deflate 压缩 |
| compresslevel | N/A（ZIP_STORED 无压缩级别） | 未指定（Python 默认 `zlib.Z_DEFAULT_COMPRESSION` ≈ level 6） |
| 代码位置 | `webdav_client.py:36` | `zotero_mcp/webdav.py: _build_zotero_zip()` |

**差异分析**：设计 §10.1 和 §10.2 两处均明确要求 `ZIP_STORED`（不压缩）。zotero-mcp 使用 `ZIP_DEFLATED` 并注释说"pyzotero uses the same compression on its own ingest path"。

**实际影响判断**：Zotero 桌面端的 zip 解压器理论上支持 STORED 和 DEFLATED 两种——标准 zip 库通常都兼容两种模式。但以下情况可能导致问题：
- 如果桌面端在同步比对时检查 zip 字节是否一致（逐字节比较），那么压缩方式不同会导致 hash 不匹配
- 如果桌面端只检查 `.prop` 中的 md5（是 PDF 原文件的 md5，不是 zip 的 md5），则压缩方式不影响兼容性

**结论**：zip 的 compress_type 差异可能不影响功能兼容性，但可能影响同步比对逻辑。需要实测。建议在实测前**暂不修改**——如果实测证明 ZIP_STORED 可用，保留（更简单、更可预测）；如果不可用再改为 ZIP_DEFLATED。

---

### 1.3 Prop XML 精确格式

| 维度 | 我们的实现 | zotero-mcp | 一致？ |
|---|---|---|---|
| XML 声明 | **无** (`xml_declaration=False`) | **无** | ✅ |
| mtime 精度 | **13 位毫秒** (`int(os.path.getmtime(f) * 1000)`) | **13 位毫秒** (`int(src.stat().st_mtime * 1000)`) | ✅ |
| hash 大小写 | **小写** (`hashlib.md5().hexdigest()`) | **小写** (`hashlib.md5().hexdigest()`) | ✅ |
| 元素顺序 | `<mtime>` 在 `<hash>` 之前 | `<mtime>` 在 `<hash>` 之前 | ✅ |
| version 属性 | `<properties version="1">` | `<properties version="1">` | ✅ |
| 换行/缩进 | 无（单行）| 无（单行）| ✅ |
| Content-Type | 由 webdav4 决定 | `text/xml; charset=utf-8` | ⚠️ 待确认 |

**字节级验证**（已在本地运行确认）：

```
我们的输出: b'<properties version="1"><mtime>1717584321000</mtime><hash>d41d8cd98f00b204e9800998ecf8427e</hash></properties>'
zotero-mcp: b'<properties version="1"><mtime>1717584321000</mtime><hash>d41d8cd98f00b204e9800998ecf8427e</hash></properties>'
字节完全一致: True
```

**结论**：prop XML 格式完全一致，无需修改。我们用 `ET.tostring(xml_declaration=False)` 生成的字节与 zotero-mcp 的 f-string 字节完全相同。

**一个潜在风险**：`ET.tostring` 在不同 Python 版本下的属性输出顺序可能不同。在 Python 3.8+ 中，`ET.Element('properties', version='1')` 生成的属性顺序是稳定的（按插入顺序），但如果未来添加更多属性需注意。当前只有一个 `version` 属性，无风险。

---

### 1.4 storage_path 与 MKCOL 行为

| 维度 | 我们的实现 | zotero-mcp |
|---|---|---|
| MKCOL | `ensure_storage_dir()` — 空路径跳过，非空先 `exists()` 再 `mkdir()` | **无 MKCOL** — 直接 PUT 到 URL |
| 路径构造 | `storage_path + "/" + key.ext` | `base_url + key.ext`（无 storage_path 概念） |
| storage_path 默认 | `/zotero`（设计 §10.1） | 直接写入 base_url 根目录 |

**差异分析**：zotero-mcp 没有 storage_path 的概念，所有文件直接放在 WebDAV URL 根目录下。我们的实现更完整，支持自定义子目录。

**MKCOL 多层目录问题**：当前 `ensure_storage_dir()` 使用 `self._client.mkdir(self._storage_path)` —— webdav4 的 `mkdir()` 默认不做递归创建。如果 `storage_path=/dav/zotero/sub`，需要逐级创建 `/dav`、`/dav/zotero`、`/dav/zotero/sub`。

**结论**：
- storage_path 为空时跳过 MKCOL：✅ 与 zotero-mcp 一致
- 多层子目录的 MKCOL：**当前未处理**，但设计 §10.1 的 normalize 规则暗示 storage_path 只有一层（如 `/zotero`）。如果需要支持多层，应改用 webdav4 的 `mkdir(path, exist_ok=True)` 或逐级创建
- zotero-mcp 不做 MKCOL 并不说明 MKCOL 是错的——它只是假设目录已存在

---

### 1.5 mtime 一致性

| 维度 | 我们的实现 | zotero-mcp |
|---|---|---|
| 来源 | `os.path.getmtime(file_path)` | `Path.stat().st_mtime` |
| 转换 | `int(... * 1000)` — 截断到毫秒 | `int(... * 1000)` — 截断到毫秒 |
| 精度丢失 | 微秒部分被丢弃 | 同 |

两者实现完全一致（`os.path.getmtime` 与 `Path.stat().st_mtime` 返回相同的浮点值）。

**桌面端"检查同步"是否会触发重传？** 这取决于：
1. Zotero 桌面端读取 `.prop` 中的 mtime 时是否与自己记录的 mtime 做精确比对
2. 如果桌面端记录的 mtime 来源不同（如 filesystem mtime vs 记录的 mtime），精度差异可能导致不匹配

**结论**：mtime 计算方式与 zotero-mcp 一致，但**桌面端交互验证仍然需要实测**。具体验证方式：上传后在桌面端点"检查同步"，观察是否触发重传。

---

### 1.6 respx 拦截 webdav4 的可行性

**结论：respx 可以拦截 webdav4.Client 的所有 HTTP 请求。**

**验证方式**（已在本地运行确认）：

```python
import respx
from webdav4.client import Client as WebDAVClient

with respx.mock:
    respx.request('PROPFIND', 'https://dav.example.com/zotero/').respond(207)
    respx.put('https://dav.example.com/zotero/ABC123.zip').respond(201)

    client = WebDAVClient(base_url='https://dav.example.com', auth=('user', 'pass'))
    response = client.http.request('PROPFIND', '/zotero/')
    # status: 207 ✅
    response = client.http.put('/zotero/ABC123.zip', content=b'fake')
    # status: 201 ✅
```

**原理**：`webdav4.http.Client` 是 `httpx.Client` 的子类（直接继承），respx 通过 monkey-patch `httpx.Client` 的 transport 实现拦截，对子类同样有效。

**对测试策略的影响**：
- ✅ 可以使用 respx 作为主要 mock 策略（DEVELOPMENT.md §6.3 的 fallback 路径 1）
- ✅ 不需要 `pytest-httpserver` 或 `wsgidav` 作为替代
- ✅ 支持 PROPFIND、MKCOL、PUT、DELETE、GET 等 WebDAV 方法的拦截
- ⚠️ respx 拦截的是 HTTP 层——webdav4 的高层方法（如 `client.exists()`、`client.mkdir()`）内部可能发多个 HTTP 请求（如 PROPFIND），需要 mock 所有相关请求

---

### 1.7 汇总：需要修改的项 vs 已确认正确的项

| 项目 | 状态 | 行动 |
|---|---|---|
| ZIP 文件名编码（base64 vs 原始名） | ❌ **与参考实现不一致** | 需实测确认；大概率需改为原始名 |
| ZIP 压缩方式（STORED vs DEFLATED） | ⚠️ 与参考实现不一致 | 需实测确认；可能不影响功能 |
| prop XML 格式 | ✅ 字节级一致 | 无需修改 |
| mtime 计算 | ✅ 逻辑一致 | 需桌面端实测确认同步行为 |
| MKCOL 行为 | ✅ 合理（参考实现无此功能） | 多层目录可能需改进 |
| respx 可拦截 webdav4 | ✅ 已验证 | 可使用 respx 作为测试 mock |

---

## 问题 2：端到端手动验证清单未执行

### 背景

DEVELOPMENT.md §9.4 和 §12.5 定义了阶段 4 的验收清单和手动测试矩阵。这些测试需要真实 Zotero 账号和 WebDAV 服务器，目前全部处于未执行状态。

### 2.1 验证清单当前状态

以下按 DEVELOPMENT.md §12.5 手动测试清单逐项列出状态和前置条件：

#### ZFS 后端测试

| 场景 | 状态 | 前置条件 | 验证方法 |
|---|---|---|---|
| `items create --attach`：桌面端能打开 PDF | ⏳ 未执行 | Zotero 账号 + API key | CLI 上传 → 桌面端同步 → 打开 PDF |
| `items attach --reuse-key`：md5 更新、key 不变 | ⏳ 未执行 | 同上 + 已有 attachment | 上传 → 修改 PDF → 重传 → 检查 API 返回 |
| `--reuse-key` 不存在时报 `ITEM_NOT_FOUND` | ⏳ 未执行 | 同上 | 传入不存在的 key → 检查退出码和错误码 |

#### WebDAV 后端测试

| 场景 | 状态 | 前置条件 | 验证方法 |
|---|---|---|---|
| 基本上传：桌面端识别并打开 | ⏳ 未执行 | WebDAV 服务器 + Zotero 配置 | CLI 上传 → 桌面端同步 → 打开 |
| `--force` 跳过 md5 检测 | ⏳ 未执行 | 同上 + 已有附件 | md5 一致时 `--force` → 检查 prop mtime 更新 |
| mtime 一致性 | ⏳ 未执行 | 同上 | 上传 → 桌面端"检查同步" → 不触发重传 |
| `library_type=group + webdav` 报错 | ⏳ 未执行 | 配置文件 | `config validate` → 退出码 1 + `UNSUPPORTED_LIBRARY_TYPE` |

#### --attach-title 语义测试

| 场景 | 状态 | 前置条件 | 验证方法 |
|---|---|---|---|
| 显式 `--attach-title` | ⏳ 未执行 | 任一后端 | 创建 → 检查父 item title 和 attachment title |
| 省略 `--attach-title` | ⏳ 未执行 | 任一后端 | 创建 → attachment title 应等于文件名 |

#### --quiet 输出契约测试

| 场景 | 状态 | 前置条件 | 验证方法 |
|---|---|---|---|
| unchanged 场景 `--quiet` 输出为空 | ⏳ 未执行 | WebDAV + `--reuse-key` | `wc -c` 检查 stdout 为 0 字节 |
| `--force` 场景 `--quiet` 输出 key | ⏳ 未执行 | 同上 + `--force` | stdout 应仅包含 attachment key |

### 2.2 测试环境搭建需求

执行上述清单需要以下环境：

1. **Zotero 账号 + API key**
   - 免费账号即可（附件存储限制 300MB，测试用小 PDF 足够）
   - 从 https://www.zotero.org/settings/keys 获取 API key

2. **WebDAV 服务器**（WebDAV 后端测试用）
   - 选项 A：自建——本地起一个 wsgidav/nginx-dav 容器
   - 选项 B：免费服务——部分 WebDAV 提供商支持免费试用
   - 选项 C：Zotero 桌面端配置的真实 WebDAV（如果已有）

3. **Zotero 桌面端**
   - 用于验证同步行为（mtime 一致性、PDF 打开等）
   - 需与测试账号同步

### 2.3 建议执行顺序

根据依赖关系和优先级，建议按以下顺序执行：

**第一批：不依赖实际 WebDAV 协议格式**
1. `library_type=group + webdav` 报错（纯配置层测试）
2. `--reuse-key` 不存在时报 `ITEM_NOT_FOUND`（ZFS 路径）
3. `--attach-title` 语义（ZFS 路径先测，与协议无关）

**第二批：ZFS 后端功能验证**
4. `items create --attach`（ZFS）
5. `items attach --reuse-key`（ZFS，重传场景）

**第三批：WebDAV 协议验证（阻塞问题 1 的解决）**
6. **协议 spike**：用 Zotero 桌面端上传 PDF 到 WebDAV，下载 zip 验证格式
7. 根据 spike 结果修复 `_build_zip`（如果 base64 假设有误）
8. CLI 上传到 WebDAV → 桌面端识别验证
9. mtime 一致性验证
10. `--force` 和 `--quiet` 场景

### 2.4 可自动化测试 vs 必须手动的测试

| 类别 | 场景 | 说明 |
|---|---|---|
| **可单元测试覆盖** | `--quiet` 输出格式、`--attach-title` 字段赋值逻辑、group+webdav 拒绝 | 不需要真实服务器，mock 即可 |
| **可集成测试覆盖** | `--reuse-key` 不存在报错、`--force` 跳过 md5 逻辑 | 用 respx mock API/WebDAV 即可 |
| **必须手动执行** | 桌面端能打开 PDF、mtime 不触发重传、base64 编码验证 | 需要真实 Zotero 桌面端 + 真实服务器 |

### 2.5 与问题 1 的关联

问题 2 中的 WebDAV 后端测试**阻塞于问题 1 的解决**。如果 zip 文件名编码或压缩方式不正确，桌面端验证必然失败。建议：

1. 先做问题 1 的**协议 spike**（用 Zotero 桌面端上传，提取 zip 分析格式）
2. 根据 spike 结果修改 `_build_zip`
3. 再执行问题 2 的 WebDAV 端到端验证

---

## 附录 A：zotero-mcp 关键代码摘录

### A.1 `_build_zotero_zip()`
```python
# 源文件: src/zotero_mcp/webdav.py
def _build_zotero_zip(file_path: str | Path) -> bytes:
    src = Path(file_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src, arcname=src.name)
    return buf.getvalue()
```

### A.2 `_build_prop_xml()`
```python
def _build_prop_xml(md5_hex: str, mtime_ms: int) -> bytes:
    return (
        '<properties version="1">'
        f"<mtime>{int(mtime_ms)}</mtime>"
        f"<hash>{md5_hex}</hash>"
        "</properties>"
    ).encode("utf-8")
```

### A.3 Upload flow
```python
# mtime calculation
mtime_ms = int(src.stat().st_mtime * 1000)

# Content-Type for prop upload
headers={"Content-Type": "text/xml; charset=utf-8"}

# URL construction (no storage_path, no base64)
zip_url = f"{base_url}{quote(attachment_key, safe='')}.zip"
prop_url = f"{base_url}{quote(attachment_key, safe='')}.prop"
```

### A.4 HTTP client
- 使用 `requests.Session`（非 httpx/webdav4）
- Basic auth via `session.auth = (username, password)`
- `session.trust_env = True`

## 附录 B：respx 拦截 webdav4 的验证记录

```
$ uv run python3 -c "..."
PROPFIND status: 207  ← respx 拦截成功
PUT status: 201       ← respx 拦截成功

原理: webdav4.http.Client 继承自 httpx.Client
      respx monkey-patch httpx.Client 的 transport
      对子类同样有效
```

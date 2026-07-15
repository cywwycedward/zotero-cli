# Zotero Web API 与 PyZotero：zotero-cli 开发者研究笔记

- 调研日期：2026-07-15
- 目标：为当前 `zotero-cli` 的 API 适配、分页、缓存、写入和错误处理提供可执行的官方依据。
- 来源范围：仅使用 Zotero 官方 Web API/开发者文档，以及 PyZotero 官方仓库 README、源码和其发布的 API 文档；没有使用论坛、博客或第三方教程。
- 标记：`[事实]` 是来源明确写出的行为；`[推断]` 是结合这些事实与本仓库现状得出的开发建议。每条外部事实均附来源和访问日期；仓库现状也附当前文件链接。

## 结论先行

1. `[事实]` 生产客户端应显式请求 Web API v3：优先发送 `Zotero-API-Version: 3`，API 基址是 `https://api.zotero.org`，用户库和群组库路径分别从 `/users/<userID>` 与 `/groups/<groupID>` 开始。[Zotero v3 入口](https://www.zotero.org/support/dev/web_api/v3/)；[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
2. `[事实]` 公共库可免认证读取；非公开库及所有写入操作需要 API key。API key 推荐放在 `Zotero-API-Key` 或 `Authorization: Bearer` 请求头，不推荐放在 URL 的 `key` 参数中。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
3. `[事实]` 多对象读取的服务端 `limit` 是 1–100，默认 25；响应通过 `Total-Results` 和 `Link` 头表达总数与下一页。`Last-Modified-Version`、`If-Modified-Since-Version`、`since` 是大库读取和增量同步的关键机制。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
4. `[事实]` 新建/更新的多对象请求最多 50 个对象；更新已有对象必须带对象 `version` 或 `If-Unmodified-Since-Version`，否则会得到 `428 Precondition Required`，版本过期则得到 `412 Precondition Failed`。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)；[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
5. `[推断]` 当前 CLI 应优先把“服务端分页/版本/条件写入/批量结果”纳入 `ZoteroAPI` 适配边界，再由 service 层做业务编排；不要在命令层自行猜测下一页、盲目重试或把 `412` 当普通服务器错误。

## 1. Zotero Web API 事实

### 1.1 URL、版本、库类型和认证

- `[事实]` Web API 所有请求都使用 HTTPS，基址为 `https://api.zotero.org`。用户库资源使用 `/users/<userID>`，群组库资源使用 `/groups/<groupID>`；user ID 与用户名不同，group ID 与群组名不同。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` v3 是当前默认且推荐用于新开发的版本。客户端可以用 `Zotero-API-Version: 3` 或 `v=3` 指定版本；生产代码推荐请求头，响应会返回 `Zotero-API-Version`。[Zotero v3 入口](https://www.zotero.org/support/dev/web_api/v3/)；[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` 公共库的读取不要求认证；访问非公开库需要 API key。写入方法需要对目标库具有写权限的 API key。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` API key 的三种传法是 `Zotero-API-Key` 请求头、`Authorization: Bearer` 请求头和 URL 查询参数 `key`；官方推荐请求头，因为 API 返回的分页 URL 可以直接使用而无需改写。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` OAuth 文档描述的是 OAuth 1.0a 的 key exchange：应用先注册 Client Key/Secret，再请求用户授权以换取 API key；可预置个人库读写、notes 读取以及所有群组的 `none`/`read`/`write` 权限。获得的 key 会持续有效，直到用户撤销，因此应按敏感凭据处理。[Zotero OAuth](https://www.zotero.org/support/dev/web_api/v3/oauth)（访问：2026-07-15）

`[推断]` 对 `zotero-cli` 而言，profile 中的 `api_key` 应只进入进程内的请求头，不应拼入日志、错误上下文、审计参数或用户可复制的 URL；若未来支持 OAuth，OAuth 只负责取得 key，API 调用仍统一走同一适配器。

### 1.2 Items、collections、搜索资源

- `[事实]` Item 端点包括全库 `/items`、顶层 `/items/top`、回收站 `/items/trash`、单项 `/items/<itemKey>`、子项 `/items/<itemKey>/children`，以及集合下的 `/collections/<collectionKey>/items` 和 `/items/top` 变体。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` Collection 端点包括全库 `/collections`、顶层 `/collections/top`、单个 collection、以及 `/collections/<collectionKey>/collections` 子集合端点。保存的搜索使用 `/searches`；它与 items 端点上的即时 `q` 查询是不同资源。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` 读取 items 时，`q` 是 quick search；`qmode=titleCreatorYear` 是默认模式，`qmode=everything` 可把全文内容纳入搜索。`itemType` 和 `tag` 支持 OR/NOT 等布尔语法，带空格或特殊字符的搜索值必须按客户端需要进行 URL 编码。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` `includeTrashed=1` 可把回收站项目纳入 item 搜索；`since=<libraryVersion>` 只返回指定库版本之后修改的对象。`sort`/`direction` 可控制排序，支持的排序字段包括 `dateAdded`、`dateModified`、`title`、`creator` 等。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）

`[推断]` CLI 的 `items search` 应显式区分普通 metadata 搜索和全文搜索，并把 `qmode` 作为内部策略而非让命令层手写 URL。`collections` 树应以 collection key 和 `parentCollection` 建树；集合成员变更本质上是 item 的 `collections` 字段变更，而不是一个独立的 item-membership 对象。

### 1.3 分页、缓存和版本

- `[事实]` 多对象读取的 `limit` 取值为 1–100，默认 25，`start` 默认 0；服务端实际返回数不超过 100。响应会带 `Total-Results`，当仍有后续结果时在 `Link` 头提供 `rel=first`、`prev`、`next`、`last` 等链接。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` `format=bib` 不支持普通排序/分页语义；需要导出的格式应按 API 的导出约束处理，不能把所有格式都当作 JSON item 分页。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` 多对象响应返回当前库的 `Last-Modified-Version`。后续多对象 GET 带 `If-Modified-Since-Version: <libraryVersion>`，且数据未变化时会得到 `304 Not Modified`；完整下载库数据后，推荐使用 `since` 获取之后的变化对象。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
- `[事实]` 版本号单调递增但不保证连续，应视作不透明整数。`If-Unmodified-Since-Version` 用于防止旧数据覆盖新数据；多对象写入按库版本判断，单对象写入按对象版本判断。[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
- `[注意：官方页面存在差异]` Basics 的 Caching 小节称单对象条件 GET 尚未支持；Syncing 又描述了单对象 `If-Modified-Since-Version` 的用法。基于这两页的冲突，稳妥做法是把多对象 `304` 作为稳定支持；单对象条件 GET 在 `zotero-cli` 中应先针对目标 API 实测并保留普通 GET 回退。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）

`[推断]` 对列表命令，优先消费响应 `Link` 的 `next` URL 或 PyZotero 的 `follow/everything`，而不是仅用 `start += limit` 猜下一页；这样可以保留服务端对分页参数的决定。若要持久化缓存，最小状态是库 ID、查询范围/参数、结果和 `Last-Modified-Version`。

### 1.4 写入、批处理和幂等

- `[事实]` JSON 响应中的 `data` 是可编辑 JSON。官方建议从 `data` 提取字段、修改后只提交可编辑数据；只提交变更字段时可用 `PATCH`，完整替换使用 `PUT`。上传完整响应时，`library`、`links`、`meta` 等外围属性不会被处理。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` 创建新 item 时应先获取 item template（可缓存），再以数组提交到 `/items`。创建或更新多个 items、collections、saved searches 时，每次最多 50 个对象；批量响应按 `success`、`unchanged`、`failed` 给出逐项状态。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` 更新已有对象时，每个对象应含 `key` 与 `version`，或请求使用 `If-Unmodified-Since-Version`。更新 item 的数组字段按完整列表解释；例如省略某个 collection key 会把 item 从该 collection 移除。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` 多个 items、collections、searches 和 tags 的删除接口每次最多 50 个；成功删除通常返回 `204 No Content` 和新的 `Last-Modified-Version`。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` `Zotero-Write-Token` 是客户端生成的随机 32 字符标识，可用于无版本写入的重复提交保护；成功请求的 token 会在服务端缓存 12 小时，同一 API key 重复使用会得到 `412`。如果写入失败，token 不会被保存；若已经使用版本条件写入，token 是多余的。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）

`[推断]` CLI 的写策略应按以下优先级实现：

1. 更新现有 item：先读取当前 `version`，只生成明确的字段 patch；提交时保留版本条件。
2. 创建/批量编辑：按 50 分块，并逐项保留 `success`、`unchanged`、`failed`，不能因为 HTTP 200 就把整批标成成功。
3. 需要安全重试的无版本写入才使用唯一 `Zotero-Write-Token`；已有版本条件的写入重试前应重新读取并重新计算 patch，不要盲目重放旧 JSON。

### 1.5 并发、冲突、错误码和重试边界

- `[事实]` Zotero 文档列出的常见错误包括：`400` 请求/JSON/字段无效，`403` API key 无效或权限不足，`404` 资源不存在，`405` 方法不允许，`500`/`503` 服务端问题，`429` 超出速率限制；条件请求可返回 `304`。写入还可能返回 `409`（目标库被锁定）、`412`（版本过期或 write token 重复）和 `428`（缺少必要的版本前置条件）。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
- `[事实]` 同步建议在每个响应检查 `Last-Modified-Version`；若远端库版本在读取过程中发生变化，应重新获取变化/删除数据，并逐步增加等待时间。写入遇到 `412` 时也应回到同步流程，而不是覆盖远端数据。[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
- `[事实]` API 可能在任意响应（包括成功响应）返回 `Backoff: <seconds>`；客户端应完成维持一致性所需的最少请求后，在该秒数内暂停进一步请求。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
- `[事实]` 收到 `429` 时应至少等待 `Retry-After` 指定时间；没有该头时使用指数退避，同时降低总体请求速率/并发。Zotero 文档建议通常不超过 4 个并发请求；`503` 也可能携带 `Retry-After`。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）

`[推断]` 推荐的 CLI 重试矩阵是：`429`/`503` 尊重 `Retry-After`，否则使用有上限的指数退避；读取遇到 `Backoff` 时更新客户端级冷却时间；`409` 可有限次等待后重试；`412` 必须转为“远端已变化/冲突”并重新读取；`400`、`403`、`404`、`405`、`428` 不应自动盲重试。错误输出应携带 status/header 的可操作信息，但绝不回显 API key。

## 2. PyZotero 官方实现与接口

### 2.1 客户端构造和传输行为

- `[事实]` PyZotero README 的基本用法是 `Zotero(library_id, library_type, api_key)`，其中 `library_type` 为 `user` 或 `group`；读取返回的 item 使用 `item['data']` 访问字段。[PyZotero README](https://github.com/urschrei/pyzotero/blob/main/README.md)（访问：2026-07-15）
- `[事实]` 官方 API 文档列出的构造参数包括 `preserve_json_order`、`locale`、`local`、可注入的 HTTP client，以及文件上传超时 `upload_timeout`。`local=True` 用于连接 Zotero Desktop 的本地 API，当前定位是只读访问。[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)；[PyZotero README](https://github.com/urschrei/pyzotero/blob/main/README.md)（访问：2026-07-15）
- `[事实]` 当前官方源码的 `Zotero` 客户端使用远程端点 `https://api.zotero.org`，本地模式使用 `http://localhost:23119/api`；默认请求头包含 `Zotero-API-Version: 3`，有 API key 时使用 `Authorization: Bearer`。[PyZotero `_client.py`](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/_client.py)（访问：2026-07-15）
- `[事实]` 官方源码在统一的请求后处理里读取 `Backoff`/`Retry-After` 并记录冷却时间，后续请求在冷却尚未结束时等待；这不等同于把所有失败请求自动重试，CLI 仍需决定哪些错误可重试。[PyZotero `_client.py`](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/_client.py)；[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）

### 2.2 关键读取接口和参数

`[事实]` PyZotero 官方 API 文档/README 暴露的核心接口如下；参数由方法关键字参数传入，或通过 `add_parameters()` 设置：[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)；[PyZotero README](https://github.com/urschrei/pyzotero/blob/main/README.md)（访问：2026-07-15）

| 用途 | PyZotero 接口 | 关键参数/返回约定 |
|---|---|---|
| 全部 items | `items(**kwargs)` | 支持 `q`、`qmode`、`itemType`、`tag`、`since`、`sort`、`direction`、`limit`、`start` |
| 顶层 items | `top(**kwargs)` | 等价于 `/items/top`；README 示例使用 `top(limit=5)` |
| 单项/子项 | `item(key)`、`children(key)` | 返回 item dict；字段通常在 `data` 中 |
| 全文内容 | `new_fulltext(since)`、`fulltext_item(itemID)` | `fulltext_item()` 返回 `content` 及 PDF 的 `indexedPages`/`totalPages` 或文本的 `indexedChars`/`totalChars` |
| 集合 items | `collection_items(key, **kwargs)`、`collection_items_top(key, **kwargs)` | 分别取集合全部项目或集合顶层项目 |
| 集合树 | `collections()`、`collections_top()`、`collections_sub(key)`、`all_collections()` | `all_collections()` 可递归得到扁平列表 |
| 搜索/标签 | `searches()`、`tags()`、`item_tags(key)` | 保存搜索与 tag 是独立资源 |
| 版本/总数 | `item_versions()`、`collection_versions()`、`last_modified_version()`、`num_items()` | 可结合 `since` 做增量读取和同步准备 |
| 非连续 key 集合 | `get_subset(itemIDs)` | 官方文档约束每次最多 50 个 item key |

`add_parameters()` 支持的常用参数集合包括 `format`、`itemKey`、`itemType`、`q`、`qmode`、`since`、`tag`、`sort`、`direction`、`limit`、`start`，以及导出相关的 `content`/`style`。PyZotero 文档说明其 JSON 读取默认会设置 `limit=100`，需要全部结果时用 `everything()`。[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)（访问：2026-07-15）

- `[事实]` Zotero 全文内容 endpoint 为 `GET <userOrGroupPrefix>/items/<itemKey>/fulltext`，其中 `itemKey` 必须是已存在的附件 item；响应为 JSON，包含 `content`，PDF 使用 `indexedPages`/`totalPages`，文本文件使用 `indexedChars`/`totalChars`。[Zotero Full-Text Content](https://www.zotero.org/support/dev/web_api/v3/fulltext_content)（访问：2026-07-15）
- `[推断]` CLI 应把全文读取作为只读的 `ZoteroAPI` 适配器方法和独立 service，不复用附件上传 backend；全文 endpoint 的 `404` 应映射为 `FULLTEXT_NOT_FOUND`，避免与普通 item `ITEM_NOT_FOUND` 混淆。

### 2.3 分页、缓存和写接口

- `[事实]` `follow()` 沿响应的 next link 取下一页；`iterfollow()` 与 `makeiter()` 提供生成器式用法；`everything(query)` 持续跟随分页直到没有 next link。官方文档也提示这些方法应只用于可返回多对象的读取方法。[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)（访问：2026-07-15）
- `[事实]` item 写接口包括 `item_template()`、`create_items()`、`update_item()`、`update_items()`、`delete_item()`；collection 写接口包括 `create_collections()`、`update_collection()`、`update_collections()`、`delete_collection()`。官方文档说明长于 50 的更新会被 `update_items()`/`update_collections()` 分块处理。[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)（访问：2026-07-15）
- `[事实]` `create_items(items, parentid=None, last_modified=None)` 接受 item dict 列表；`update_item(item, last_modified=None)` 在未显式传 `last_modified` 时使用 item 自身的 version；`check_items()` 可通过 `item_fields()` 先校验未知字段。[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)（访问：2026-07-15）
- `[事实]` 新代码推荐从 `pyzotero import Zotero` 导入；`pyzotero.zotero` 仍保留为向后兼容的 re-export 模块。[PyZotero `zotero.py`](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/zotero.py)；[PyZotero README](https://github.com/urschrei/pyzotero/blob/main/README.md)（访问：2026-07-15）

## 3. 面向当前 zotero-cli 的具体建议

### 3.1 现状（仓库事实）

- `[事实]` 所有 Web API 调用集中在 `ZoteroAPI`，构造 `Zotero` 实例并统一翻译 PyZotero 异常。[适配器](../src/zotero_cli/adapters/zotero_api.py)（访问：2026-07-15）
- `[事实]` 当前 item 列表/搜索的适配器默认使用 `limit=100`、`start=0`，service 还会调用总数和库版本；DOI 查找在 service 层手动递增 `start`。[适配器](../src/zotero_cli/adapters/zotero_api.py)；[ItemService](../src/zotero_cli/services/item_service.py)（访问：2026-07-15）
- `[事实]` 当前 item 删除、collection 成员增删、tag 增删/重命名主要按单 item 循环；tag 重命名/删除路径还直接调用 `items(limit=10000)`。[ItemService](../src/zotero_cli/services/item_service.py)；[CollectionService](../src/zotero_cli/services/collection_service.py)；[TagService](../src/zotero_cli/services/tag_service.py)（访问：2026-07-15）
- `[事实]` 当前适配器把 PyZotero 的 `PreConditionFailedError` 归为通用 `ApiServerError`，把 `TooManyRequestsError` 归为 `ApiRateLimitError`。[适配器](../src/zotero_cli/adapters/zotero_api.py)（访问：2026-07-15）
- `[事实]` 当前 CLI 的全文读取命令为 `items fulltext <attachment-key>`，通过 `ZoteroAPI.fulltext_item()` 获取正文，默认输出 raw content，`--json` 返回 envelope，`--output` 写入 UTF-8 文本文件。[适配器](../src/zotero_cli/adapters/zotero_api.py)；[FulltextService](../src/zotero_cli/services/fulltext_service.py)；[items command](../src/zotero_cli/commands/items.py)（访问：2026-07-15）

### 3.2 推荐改进顺序（推断）

1. **先修分页边界。** Zotero 服务端多对象 `limit` 上限是 100，因此不要把 `limit=10000` 当成“取全库”；用 PyZotero 的 `everything(zot.items(...))`、`follow()` 或显式 Link 循环。这个建议直接基于 API 的 1–100 约束和 PyZotero 的分页接口。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)（访问：2026-07-15）
2. **让适配器拥有请求政策。** 显式固定 v3、统一使用 bearer/header 认证、记录 `Backoff`/`Retry-After`、解析 `Link`/`Total-Results`/`Last-Modified-Version`；service 层只消费已解析的领域结果。这样能避免命令层重复实现协议细节。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[PyZotero `_client.py`](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/_client.py)（访问：2026-07-15）
3. **增加可选的库版本缓存。** 对重复列表查询保存查询范围及 `Last-Modified-Version`，下一次多对象 GET 使用 `If-Modified-Since-Version`；需要同步/刷新时使用 `since`。`304` 时复用本地结果；首次实现可以只缓存 items/collections，避免一次引入完整同步器。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)；[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
4. **把批量写入作为一等路径。** 对 item 更新、collection 创建/删除、tag 的批量处理按 50 分块，保留每个对象的 success/unchanged/failed；集合成员操作应读取 item 当前 `data.collections`，只改列表后批量提交 item，而不是为每个成员单独发一次更新。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)；[PyZotero API 文档](https://pyzotero.readthedocs.io/en/latest/index.html)（访问：2026-07-15）
5. **保留冲突语义。** 新增 `API_CONFLICT`/`API_PRECONDITION_REQUIRED` 一类 CLI 错误，把 `412` 与 `500` 分开；在 `412` 后重新 GET、重新应用用户明确请求的 patch，再由用户或命令策略决定是否提交，绝不把旧快照直接覆盖回去。[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)；[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)（访问：2026-07-15）
6. **按响应头实现有限重试。** 只对 `429`/`503`/传输失败做有上限重试，尊重 `Retry-After`；所有请求都检查 `Backoff`。`409` 可做短暂、有限次重试；`400`、`403`、`404`、`405`、`412`、`428` 默认直接报告可操作错误。[Zotero Basics](https://www.zotero.org/support/dev/web_api/v3/basics)（访问：2026-07-15）
7. **修正错误映射和失败信息。** 当前 `PreConditionFailedError -> ApiServerError` 会丢失“版本冲突”语义，批量失败规范化也应保留服务端实际错误代码/消息，而不是统一成 `INVALID_ITEM_TYPE`。这是基于当前代码与官方批量响应结构的实现建议。[适配器](../src/zotero_cli/adapters/zotero_api.py)；[Zotero Write Requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)（访问：2026-07-15）
8. **为 CLI 输出协议级元数据。** 在 `--json` 的 meta 中可稳定提供 `library_id`、`library_version`、请求范围、分页位置、是否来自 `304`/缓存和重试次数；人类输出只展示简洁提示。这样既方便 agent 消费，也便于诊断并发和限流问题。[Zotero Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)；[仓库结果模型](../src/zotero_cli/models/results.py)（访问：2026-07-15）

## 4. 实现检查清单

- [ ] 所有远程请求固定 `Zotero-API-Version: 3`，API key 只走请求头。
- [ ] 多对象读取 `limit <= 100`；分页优先使用 `Link`/`follow()`，不要使用超大 `limit` 假定一次取全。
- [ ] 保存 `Last-Modified-Version`；重复读取使用 `If-Modified-Since-Version`，增量读取使用 `since`。
- [ ] 写入 item/collection 前保留 `version` 或使用 `If-Unmodified-Since-Version`；`PATCH` 只发送明确改变的字段。
- [ ] 批量写入/删除每批不超过 50，逐项保存成功、未变化和失败。
- [ ] 识别 `409`、`412`、`428`，不要把冲突当普通服务器故障自动覆盖。
- [ ] 尊重任意响应的 `Backoff`，`429`/`503` 尊重 `Retry-After`；并发通常不超过 4。
- [ ] 不把 API key 写入 URL、日志、审计参数或错误信息。
- [ ] 为 Basics 与 Syncing 对单对象条件 GET 的文档差异保留测试和普通 GET 回退。
- [x] 全文读取使用附件 item key，保留 `content` 与索引进度字段，并将全文 endpoint 的 404 与普通 item 404 区分。

## 来源索引（均为一手来源，访问日期：2026-07-15）

### Zotero

- [Web API v3 入口](https://www.zotero.org/support/dev/web_api/v3/)
- [Web API Basics：URL、认证、资源、搜索、分页、缓存、限流、状态码](https://www.zotero.org/support/dev/web_api/v3/basics)
- [Web API Write Requests：JSON、item/collection/search 写入、批处理、write token](https://www.zotero.org/support/dev/web_api/v3/write_requests)
- [Web API Syncing：版本、条件写入、并发和冲突流程](https://www.zotero.org/support/dev/web_api/v3/syncing)
- [Web API Full-Text Content：全文 endpoint、返回字段和附件约束](https://www.zotero.org/support/dev/web_api/v3/fulltext_content)
- [OAuth Key Exchange：key exchange 与权限参数](https://www.zotero.org/support/dev/web_api/v3/oauth)

### PyZotero

- [官方仓库 README](https://github.com/urschrei/pyzotero/blob/main/README.md)
- [官方源码：`_client.py`](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/_client.py)
- [官方源码：`zotero.py` 兼容导出](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/zotero.py)
- [官方项目文档：API 方法与参数](https://pyzotero.readthedocs.io/en/latest/index.html)
- [官方项目元数据/发布配置：`pyproject.toml`](https://github.com/urschrei/pyzotero/blob/main/pyproject.toml)

# LedgerDesk 0.7 架构与契约

0.7 使用 schema v7，新增处理版本与审计查询索引；批量处理契约见 [批量处理与操作记录](BULK_REVIEWS.md)，查询边界见 [大批次查询与版本契约](PAGINATION.md)。备份和恢复规则见 [本地数据保护与恢复](DATA_MANAGEMENT.md)。

项目保持 Python 标准库运行方式，按实际职责逐步拆分。`store.py` 仍提供旧调用入口，HTTP 单项处理从 0.7 起须携带运行和处理版本；原 Python 调用签名保留，新增可选并发参数。

```mermaid
flowchart TD
    UI["浏览器 / CLI"] --> HTTP["HTTP 参数和错误响应"]
    HTTP --> Store["Store 兼容入口"]
    Store --> App["application：核对用例与报告"]
    App --> Domain["domain：金额、映射、核对、筛选、历史差异"]
    Store --> Repo["persistence：模板、运行记录、连接、迁移、备份"]
    App --> Repo
    Repo --> DB["SQLite"]
```

## 模块职责

| 模块 | 职责 |
| --- | --- |
| `domain/money.py` | 人民币元与整数分转换、精度和边界 |
| `domain/mappings.py` | 完整字段映射、显式渠道别名和冲突校验 |
| `domain/reconciliation.py` | 按订单聚合、净额、重复流水、证据版本 |
| `domain/filters.py` | 顶部分类、异常类型、状态和搜索的组合语义 |
| `domain/history.py` | 保存结果之间的新增、消失和变化 |
| `domain/errors.py` | 用户输入错误及稳定错误码 |
| `application/reconciliation.py` | 在事务内加载输入、核对、写入运行及审计 |
| `application/reports.py` | CSV 格式、金额显示和公式转义 |
| `application/data_management.py` | 手动备份管理、限定路径选择和新目录恢复 |
| `persistence/diagnostics.py` | 支持版本、结构、完整性、外键和数量的只读检查 |
| `persistence/database.py` | 数据库生命周期、事务和在线备份 |
| `persistence/migrations.py` | 显式升级路径、外键验证和版本保护 |
| `persistence/templates.py` | 模板修订、复制、删除和文件导入导出 |
| `persistence/runs.py` | 有效输入身份、核对运行加载与存储 |
| `persistence/result_queries.py` | 运行范围校验、SQL 筛选、计数和有界摘要查询 |
| `domain/result_summary.py` | 从不可变结果提取不含源行的查询摘要 |
| `domain/reviews.py` | 处理状态、共享备注、选择范围和版本参数校验 |
| `application/batches.py` | 批次创建、标签和归档事务 |
| `application/imports.py` | 整份导入、备份、撤销与原子替换事务 |
| `application/reviews.py` | 单项与批量处理、运行和乐观版本检查、事务回滚 |
| `persistence/batches.py` | 批次状态与列表读写 |
| `persistence/imports.py` | 有效文件、源行写入和输入版本推进 |
| `persistence/reviews.py` | 证据范围内的处理读写与整数版本 |
| `persistence/audit.py` | 审计追加、类型筛选和固定事件上限分页 |
| `static/reviews.js`、`static/batches.js`、`static/audit.js` | 处理选择与详情、批次列表设置、审计分页控制器 |
| `store.py` | 公共兼容入口与结果查询编排 |
| `config.py` | JSON 配置验证和默认值；校验不创建数据目录 |

领域层不依赖 SQLite、HTTP 或页面。测试同时检查业务行为和这一依赖方向。批次、导入、处理、运行和模板已建立仓储边界；应用服务持有事务，Store 保留旧入口及结果查询编排。

## 模板和渠道别名

模板修订从 1 开始。同名称、同数据侧再次保存会增加修订号；导入文件保存当时的映射和别名，因此模板更新不改变历史输入。

字段映射必须包含数据侧的全部标准字段，每个字段对应不同的非空列。列名保持原始大小写，应用到新文件时找不到的列留空，须重新选择。

渠道别名只执行一次精确映射，不自动合并大小写、不递归追踪别名链。去除首尾空白后原渠道重复会被拒绝。新源行保存原渠道和规范化渠道；旧库没有保存原渠道时保持未知，不通过反向猜测补值。

模板文件格式：

```json
{
  "format": "ledgerdesk.mapping-templates",
  "version": 1,
  "templates": [
    {
      "name": "合成业务单",
      "side": "orders",
      "mapping": {"order_id": "订单号", "amount": "金额", "channel": "渠道"},
      "channel_aliases": {"微信": "wechat"}
    }
  ]
}
```

模板文件最多 100 条。导入先验证全部条目，再在一个事务中保存；遇到重复或已存在的名称和数据侧时整份拒绝，不覆盖本机模板。文件不包含本机数据库 ID、路径或源账单。

## 核对和历史

核对使用整数分计算。输入版本变更后生成新的运行；输入未变时复用同次运行。跨订单重复流水属于证据的一部分，相关证据变化会使原处理状态失效。

历史详情按批次和运行 ID 一起校验，不能读取另一批次的运行。传入不存在的运行必须返回错误，不能把缺失版本当成空结果参与比较。

0.4 新生成的结果保存**运行当时**的处理状态与备注快照。之后填写的备注不会改写旧快照。此前的结果缺少快照，历史页显示“未记录”；不能从当前备注推测过去状态。比较同时显示金额、异常、源证据和有记录的处理快照变化。

历史列表默认显示最近 30 次，当前页面为逐次相邻版本比较；服务端支持同批次任意两个有效运行 ID。历史源行和结果为只读。

## 筛选与导出

“当前筛选”组合以下条件：顶部分类、异常类型、处理状态、订单号或渠道搜索。各条件取交集。`outstanding` 表示有差异且状态为待处理或处理中；金额一致的记录属于“无需处理”。搜索去除首尾空白后不区分大小写。

导出链接携带页面显示的运行 ID。若另一页面已经运行了新核对，服务端拒绝旧链接并要求刷新；过期源数据仍然禁止导出。CSV 继续使用 UTF-8 BOM 和用户文本公式转义。

## 批次与配置

归档不删除数据，也不增加输入版本。归档批次允许查看及导出，禁止追加、撤销、替换、核对与备注；恢复后继续使用。标签最多 20 个，每个最多 30 字，去除首尾空白并去重。

配置使用 `config.example.json` 的 version=1 格式，命令行显式参数优先。相对数据目录相对于配置文件解析。未知字段、错误类型、非法端口和未来配置版本会被拒绝。`--check-config` 只验证并打印解析结果，不打开数据库。

## 数据库和错误响应

schema v7 保留既有全部原列与记录；v6 → v7 增加处理版本与审计索引，较早升级同时建立摘要查询表并回填结果；v5 中的原渠道、模板修订、标签与归档字段继续保留。迁移前使用 SQLite 在线备份；DDL、版本号和外键校验位于同一事务，失败则回滚。

API 错误结构统一为：

```json
{"error": "可读提示", "code": "invalid_mapping", "errors": []}
```

主要错误码包括 `invalid_input`、`invalid_mapping`、`invalid_aliases`、`invalid_filter`、`stale_result`、`review_conflict`、`invalid_revision`、`invalid_selection`、`batch_archived`、`not_found`、`conflict`、`forbidden` 和 `internal_error`。异常详细堆栈只进入本机日志。

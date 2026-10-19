# 本机 API 入口

服务固定为回环 HTTP。GET 要求可信 Host；所有 POST 要求 JSON、当前页面会话 token 和允许的来源。错误结构为 `error`、`code`、`errors`，不会把服务器异常堆栈返回页面。

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `/api/workspace` | GET | 独立批次工作台，分页、归档范围 |
| `/api/rules` | GET/POST | 规则修订列表或创建 |
| `/api/batches/ID/rule` | GET/POST | 读取或选择规则 |
| `/api/batches/ID/statistics` | GET | 同筛选的总计与渠道页 |
| `/api/batches/ID/cases/KEY/info` | GET | 不含源数组的详情摘要 |
| `/api/batches/ID/cases/KEY/evidence` | GET | source/duplicate 证据页 |
| `/api/batches/ID/runs/RUN/cases/KEY/info` | GET | 历史只读摘要 |
| `/api/batches/ID/runs/RUN/cases/KEY/evidence` | GET | 历史只读证据页 |
| `/api/report-profiles` | GET/POST | 列目录与不可变报告配置 |
| `/api/batches/ID/report` | GET | 当前筛选 CSV 或 HTML 流 |
| `/api/jobs` | GET/POST | 任务页或固定类型提交 |
| `/api/jobs/queue` | POST | 最多100个批次的原子排队 |
| `/api/jobs/ID/cancel`、`retry` | POST | 任务控制 |
| `/api/jobs/ID/download` | GET | 已完成任务的专属报告 |
| `/api/filters` | GET/POST | 常用筛选与版本检查 |
| `/api/filters/delete` | POST | 按 ID 与版本删除筛选 |
| `/api/backup-policy` | GET/POST | 带修订的备份策略 |
| `/api/backup-policy/prune` | POST | 明确执行已登记备份保留策略 |

新查询通常支持 `page`、`page_size`，每页上限100；运行相关请求使用 `run_id`。统计可用 `historical=true` 读取旧快照；详情历史路径显式包含运行ID。

原有导入、处理、审计、批次和历史接口保留，详见 [导入向导](IMPORT_WIZARD.md)、[批量处理](BULK_REVIEWS.md) 和 [分页契约](PAGINATION.md)。

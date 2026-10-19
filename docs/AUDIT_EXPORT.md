# 操作记录导出

批次操作记录可以从页面、HTTP 或 CLI 导出 CSV/JSONL。导出使用第一次请求时固定的 `until_id`，随后新增的操作不会挤进同一份文件；事件仍按批次和可选操作类型筛选。

CSV 使用 UTF-8 BOM，列为事件 ID、操作键、中文操作名、UTC 时间、事件上限和 JSON 内容。JSONL 每行一个对象，适合本机后续分析。导出保留本机审计 payload，文件写入本地，不自动上传。

```powershell
python -m ledgerdesk audit-export BATCH_ID --out .\exports\audit.csv
python -m ledgerdesk audit-export BATCH_ID --format json --action review --out .\exports\reviews.jsonl
```

HTTP 路径为 `/api/batches/<批次ID>/audit-export?format=csv&action=all&until_id=...`，仍要求回环 Host、页面会话 token 和允许的 Origin。未知格式、操作类型、批次或负事件上限返回结构化错误。

导出的 payload 可能包含处理备注和订单标识，因此不要把本地导出放进公开仓库。源码发布清单只包含导出实现和测试，不包含任何运行数据或导出文件。

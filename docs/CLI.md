# 业务命令行

全局参数放在子命令之前。例如 `python -m ledgerdesk --data-dir ./test-data stats`。输出为 JSON，失败以非零退出码结束。普通业务命令不打开浏览器。

| 命令 | 用途 |
| --- | --- |
| `batches list/create/archive/restore` | 批次管理 |
| `imports add/revoke` | 标准 CSV 导入、原子替换与撤销 |
| `reconcile BATCH_ID` | 同步核对 |
| `stats [BATCH_ID]` | 工作台或渠道统计 |
| `report BATCH_ID --out FILE` | 流式 CSV / HTML |
| `profiles list/columns/create` | 报告配置修订 |
| `rules list/create/select` | 规则版本与批次选择 |
| `reviews set/bulk` | 带运行与处理版本的人工处理 |
| `filters list/save/delete` | 常用筛选及乐观修订 |
| `jobs list/get/submit/cancel/retry/work` | 本机任务 |
| `audit BATCH_ID` | 类型筛选与稳定上限分页 |
| `evidence BATCH_ID CASE_KEY` | 源证据页 |
| `history BATCH_ID` | 历史或分页比较 |
| `maintenance policy/set-policy/backup/prune` | 备份策略和维护 |

每组具体参数使用 `--help` 查看。`--backup`、`--restore`、`--diagnose`、`--check-config` 的原入口保留，不能与业务子命令组合。

除创建批次外，业务读取不会创建缺失数据库。打开已存在旧库可能按标准启动规则先备份再迁移；只读诊断请使用 `--diagnose`。

```powershell
python -m ledgerdesk --data-dir ./trial batches create "合成验证"
python -m ledgerdesk --data-dir ./trial imports add BATCH_ID orders ./samples/orders.csv
python -m ledgerdesk --data-dir ./trial imports add BATCH_ID payments ./samples/payments.csv
python -m ledgerdesk --data-dir ./trial reconcile BATCH_ID
python -m ledgerdesk --data-dir ./trial report BATCH_ID --out ./exports/new.csv
```

模糊字段需要明确的映射 JSON 文件；别名使用 `--aliases FILE`。CLI 导入仍执行整份校验；旧直接入口不承诺预检凭据的一致性额外保证。

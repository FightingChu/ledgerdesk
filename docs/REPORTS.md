# 报告与流式导出

CSV 和 HTML 共用有序列配置。报告配置按名称创建不可变修订，旧配置保持原顺序。默认 CSV 保留原来的 12 列、UTF-8 BOM 和公式转义行为。

当前筛选导出包含所有匹配记录，不限于当前页。服务端在第一个响应块前检查批次、最新运行、源数据和配置；之后保持同一 SQLite 只读快照，避免一份报告混合多个备注版本。

CSV 每块最多 100 行。HTML 同样按 100 行分块，并嵌入固定打印样式，可作为独立文件打开。用户文本按 HTML 转义，固定样式通过 CSP 哈希放行，不允许任意内联脚本。

选择的列可以包括规则名称、修订、容差、运行 ID 和证据指纹。旧结果没有记录的规则显示“未记录”。显示配置不会重新计算金额，也不改变人工状态。

直接响应通过 `X-LedgerDesk-Run` 与Base64URL编码的 `X-LedgerDesk-Report` 头携带同次运行/规则/筛选说明；CLI可使用 `--metadata-out new.json` 保存说明。后台报告另可下载说明JSON，包含文件哈希。

后台报告写入本机任务专属文件，先生成临时文件，完成后以不覆盖方式发布。任务结果保存大小和 SHA-256，下载限定为该任务拥有的已完成文件。

```powershell
python -m ledgerdesk profiles columns
python -m ledgerdesk profiles create "复核" --columns order_id,channel,difference,note,run_id
python -m ledgerdesk report BATCH_ID --out new-report.csv --profile-id PROFILE_ID
python -m ledgerdesk report BATCH_ID --out new-report.html --format html
```

已有输出文件不会覆盖。网络下载中断可能产生不完整的客户端文件；后台报告只有完整生成后才发布。长时间直接导出会保持读快照，期间 WAL 可能增长。

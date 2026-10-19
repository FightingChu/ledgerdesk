# 规则版本与证据

规则由名称、修订号和整数分容差组成。默认规则容差为零，保留早期版本的精确核对身份；打开旧库不会因此强制改写原运行。

同名创建生成新 ID 与新修订，旧修订不更新。批次选择一个明确修订后，核对身份包含该规则快照。新运行和每条结果保存快照；旧运行没有记录的快照保持未知。

仅当原异常恰好为金额不一致，且非零差额绝对值不超过容差时，显示“容差内待复核”。不会放行重复业务单、重复流水、单边缺失或输入币种错误，不自动标记金额一致或已处理。

显式切换规则属于证据变化，变化的处理状态回到待处理；历史备注与历史快照保留。应用规则之后需要重新核对，旧页面不能直接处理或导出已过期结果。

```powershell
python -m ledgerdesk rules create "分位复核" --tolerance-cents 1
python -m ledgerdesk rules list
python -m ledgerdesk rules select BATCH_ID RULE_ID
python -m ledgerdesk reconcile BATCH_ID
```

`RULE_ID=default` 恢复默认规则。容差必须为 0～1000000 的整数分，布尔值、负数和小数不接受。归档批次不能切换规则。

# 本机任务队列

支持核对、报告与备份三种固定任务，不执行用户传入的命令或任意文件路径。任务保存在 SQLite，执行器在本机服务启动时运行，不依赖外部队列。

状态为 queued、running、succeeded、failed、cancelled、interrupted。每个工作空间使用 OS 文件锁，只允许一个执行器进行恢复与领取；SQL 写事务确保一个任务不会被同时领取两次。

核对和报告记录排队时的输入身份，执行前重新检查。核对还在实际写事务内检查身份，输入变化时失败，请提交新任务。报告绑定固定运行和不可变配置。

取消等待中的任务立即生效；运行中取消在安全检查点生效。已经提交的核对不会因迟到的取消请求而撤销。失败、取消和中断可明确重试，成功任务不能直接重试；重试仍要求原输入身份有效。

请求标识用于同参数去重，重复提交返回同一任务；同标识用于不同任务参数会拒绝。批次队列最多 100 个不重复批次，一次提交在同一事务中完成。

重启时持有工作空间锁的执行器把未完成任务标为中断。如果报告已完成发布且文件哈希符合已登记结果，可恢复为成功；临时文件只按已登记任务清理。

```powershell
python -m ledgerdesk jobs submit reconcile --batch-id BATCH_ID --request-id REQUEST_ID
python -m ledgerdesk jobs list
python -m ledgerdesk jobs work --once
python -m ledgerdesk jobs cancel JOB_ID
python -m ledgerdesk jobs retry JOB_ID
```

`jobs work` 在没有待执行任务时退出。网页执行器持续等待新任务。进度以当前阶段和完成步骤表示，不把核对内部遍历伪装为精确百分比。

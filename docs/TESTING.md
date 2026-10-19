# 验证层次

所有自动测试使用临时数据库或明确的合成 fixture，不打开默认业务库。`tests/support` 提供共享工作空间与真实回环 HTTP 生命周期；测试结束必须释放服务器、连接、线程和文件锁。

领域测试验证金额、异常、容差边界和依赖方向；持久化测试验证事务、回填与数据保留；应用测试验证运行身份、报告快照、任务和保留策略；HTTP/CLI 测试验证实际入口。

`tests/golden` 的十二组独立合成账单和人工期望共同覆盖规则、SQL 统计、流式报告与后台报告任务。期望不从实现生成，不以复制用例增加数量。

```powershell
python -m unittest discover -s tests -q
python scripts/check_boundaries.py
python scripts/check_js.py
python scripts/verify_examples.py
python scripts/local_smoke.py
python scripts/build_release.py
python scripts/verify_release.py
```

CI 在 Windows/Ubuntu 的 Python 3.10/3.12 上执行测试、JavaScript 语法和干净源码包验证。浏览器人工验证包括实际导入、规则切换、统计、报告编辑、任务下载、源行翻页和窄屏。

默认库升级另做备份与副本原列逐行比对。本机工程通过不等于客户验收、真实渠道兼容或生产压力验证。

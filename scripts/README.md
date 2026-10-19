# 工程工具

| 脚本 | 行为 |
| --- | --- |
| `build_release.py` | 按显式清单构建并逐字节验证源码ZIP |
| `verify_release.py` | 在干净解压目录执行完整测试 |
| `check_release_manifest.py` | 跟踪文件、允许清单和已知内部路径检查 |
| `check_boundaries.py` | 递归领域依赖方向检查 |
| `check_js.py` | 对发布清单中的全部JS做Node语法检查 |
| `verify_examples.py` | 配置示例与示例金样输入语法 |
| `local_smoke.py` | 临时库、临时端口的完整回环流程 |
| `check_migration.py` | 只迁移副本并比较全部原列摘要 |
| `generate_synthetic.py` | 在新目录生成两侧合成CSV，不覆盖 |
| `benchmark.py` | 合成批次的分阶段耗时与Python分配峰值 |
| `reproducible_release.py` | 固定时间戳的两次包字节一致性 |

输出报告、生成文件、备份和性能记录保存在本机，不纳入源码文件规模。工具不会发送消息、上传账单或发布远端发行版。

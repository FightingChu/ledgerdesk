# 发行步骤

1. 核对版本定义、公开变更、接口与实际功能一致。
2. 审阅每个新增文件的职责，更新显式 `RELEASE_FILES`；不递归收集用户 CSV。
3. 运行完整测试、依赖方向、JS、示例与临时工作流检查。
4. 对旧库副本做迁移、原列摘要、完整性与外键验证。
5. 完成新增页面的浏览器与窄屏验证，关闭临时服务和页面。
6. 构建源码包，逐文件比较字节，在干净目录运行全部测试。
7. 提交明确的公开文件，同步 GitHub/Gitee，核对两端 HEAD 和 CI。
8. 在本地交接记录中保留提交、包 SHA-256、实际文件数和未完成边界。

```powershell
python scripts/check_release_manifest.py
python scripts/reproducible_release.py
python scripts/build_release.py
python scripts/verify_release.py
```

固定 `SOURCE_DATE_EPOCH` 时源码包可重复生成。最后一个构建会写 `dist/release.json`，以该清单为包版本、数量和哈希来源。`dist`、数据库、备份和内部验证记录不提交。

版本发布需同时核对格式契约、回归结果和使用反馈。

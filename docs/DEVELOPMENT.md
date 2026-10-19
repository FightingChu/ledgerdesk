# 开发入口

产品运行依赖 Python 标准库，Node.js 仅用于开发语法检查。保持 `Store` 兼容入口，HTTP 和 CLI 通过应用服务调用同一业务规则。

新增功能顺序：定义可验证行为与数据身份，写能验证风险的测试，再实现领域/事务/页面。迁移单独列出版本路径，使用旧 fixture 与失败注入验证回滚。

领域层不能依赖 SQLite、HTTP 或页面，`scripts/check_boundaries.py` 递归检查子包。适配器必须有实际解析使用者，不为将来渠道创建空模块。

新增静态文件需加入允许列表、HTML 引用和发布清单。新增测试子包应检查 unittest 发现，避免目录重组导致测试数量悄悄减少。

```powershell
python scripts/check_boundaries.py
python scripts/check_js.py
python -m unittest discover -s tests -q
```

提交前用明确文件清单，保留本机的内部交接和验证记录。使用者文件直接排除提交，不通过脱敏后纳入源码来替代排除。

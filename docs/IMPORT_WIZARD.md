# 0.8 导入向导与标准 CSV 适配

导入和替换使用同一个四步流程：文件预览、字段确认、整份校验、最后确认。前三步不写入业务数据。单文件继续限制为 5 MiB、10000 行、80 列，每字段最多 2048 字符。

## 使用流程

1. 选择文件，查看编码、行数、列数和前五行。支持 UTF-8、UTF-8 BOM、GB18030。
2. 检查字段、人民币净额口径和渠道别名。多个候选列和未识别字段明确提示；完整匹配的模板列为建议，须人工选择，模板不会自动套用。
3. 勾选确认后检查全部行。存在无效行时整份不可导入；错误每页 25 行，支持翻页和下载全部错误 CSV。错误报告仅含源行号与问题描述，保留在用户本机。
4. 校验通过后再次确认文件、数据侧、映射、别名及替换原因。提交时重新校验，并在事务内检查当前批次与校验凭据。

引号不闭合、列数不一致、超出文件限制等结构错误会直接阻止预览或校验；分页用于可逐行定位的业务错误。多行引号字段的行号沿用 CSV 读取器的物理结束行号。无效文件不会部分导入。

## 标准适配协议

`adapters/base.py` 定义预览和校验协议，`registry.py` 只接受已实现的精确身份。目前只有 `standard_csv` v1；这表示本工具原有标准输入约定，不代表适配微信或支付宝原始文件。

`ingestion/reading.py` 统一编码、CSV 和源行号；`currency.py` 统一币种策略；`mappings.py` 提供字段候选和模板覆盖建议；`validation.py` 执行原有金额、标识和收退款规则。预览、完整校验和最终导入使用这些共用实现。

`ledgerdesk.imports.preview`、`parse` 和 `decode_file` 继续提供兼容入口。旧 `parse` 失败时仍仅携带前 30 条错误；新的校验接口提供全部错误的分页访问。未知适配器或版本返回 `unsupported_adapter`，不自动降级或猜测格式。

## HTTP 契约

`POST /api/preview` 接受 `side`、Base64 `content`，可明确提供 `adapter_id` 和整数 `adapter_version`。返回原有预览字段，并增加 `encoding`、`adapter`、`field_candidates`、`missing_fields`、`template_suggestions`。建议模板只表示全部映射列存在，不证明金额或渠道语义正确。

以下路径以 `/api/batches/<批次ID>` 为前缀，均要求本机会话 token、JSON 和允许的请求来源：

| POST 路径 | 行为 |
| --- | --- |
| `/validate-import` | 整份校验，返回错误页、行数、适配信息和通过时的 `receipt` |
| `/import-errors` | 相同输入的全部行错误 CSV，UTF-8 BOM，不受当前错误页限制 |
| `/import` | 保留原导入参数，新增可选 `adapter_id`、`adapter_version`、`receipt` |

校验参数与导入一致：`side`、`filename`、`content`、`mapping`、`channel_aliases`、`replace_id`、`reason`；适配器默认 `standard_csv` v1。校验另接受整数 `page`、`page_size`，每页上限 100，默认 25。

校验响应包括 `valid`、`row_count`、`valid_rows`、`error_count`、`errors`、`page`、`page_size`、`total_pages`、`file_sha256`、`encoding`、`adapter`、`currency`、`receipt`、`expires_in`。存在行错误时请求正常返回 HTTP 200，`valid=false` 且无凭据；结构、映射或参数非法时返回 HTTP 400。

## 校验凭据与事务

凭据有效期 600 秒，绑定批次 ID、输入版本、文件原字节 SHA-256、文件名、数据侧、完整映射、规范化别名、替换目标和原因，以及适配器版本。服务端使用独立随机密钥签名，不缓存上传原文；服务重启后旧凭据失效。

确认前更改任一有效输入，或批次已发生另一份导入/撤销/替换，将返回 `stale_validation`。页面返回字段步骤，须重新确认并校验。归档批次始终拒绝导入。最终版本检查与文件切换在同一个写事务中完成；替换仍先备份，失败保留原有效文件。

旧 Python 和 HTTP 调用可省略凭据，继续在最终提交时校验整份文件；它们没有“预检后输入保持一致”的额外保证。新向导始终提交凭据。凭据用于一致性检查，不替代会话验证，也不是可以重放的导入任务 ID。

## 存储与边界

schema v8 为导入记录增加 `adapter_id`、`adapter_version`。新标准导入记录为 `standard_csv` / 1；旧导入的版本为 `null`，不根据当前规则补造历史版本。升级前备份，增加列和版本号事务提交，原列、源行、结果、人工处理与审计保持原值。

校验和错误翻页会重新读取完整输入，遵循单文件容量限制；导入以标准 CSV 的同步校验与确认流程执行，原始 CSV 由使用者保管。只有最终标准化源行和文件指纹入库，错误下载及原文件不进入公开源码包。

# kb-ingestion-quality Proposal

## Why

当前文档入库链路存在质量与可运维短板：解析后文本不做清洗（PDF 解析噪声原样进入 chunk）、OCR 仅作为解析失败兜底而非主路径、上传接口同步全流程处理导致大文件阻塞请求线程、答案只能追溯到 doc_name 无法精确到 chunk/页码，且没有任何检索质量度量来量化优化效果。

本次在 P0/P1 基础上，补齐入库质量治理与可观测性。

## What Changes

- **文本清洗**：解析后对文本做规范化（合并空白、去页眉页脚、去控制字符）。
- **异步入库**：文档分块与向量化改异步执行，避免上传阻塞。
- **OCR/表格解析主路径**：扫描件先 OCR 再进入解析，表格保留结构。
- **引用溯源**：答案来源精确到 chunk/页码级。
- **检索质量评估**：新增命中率等评估指标脚本。

## Capabilities

### New Capabilities

- `kb-retrieval-evaluation`: 检索质量评估能力，提供检索命中率等可量化指标。

### Modified Capabilities

- `file-upload-management`: 文档处理新增文本清洗与异步处理行为。
- `rag-chain`: 新增 chunk 级引用溯源行为。

## Impact

- 代码：`framework/upload/document_parser.py`（清洗/OCR/表格）、上传管线（异步）、`framework/rag/chain.py`（引用）、新增评估脚本。
- 依赖：异步任务机制（Celery 或线程池，按现有技术栈选型）。
- 无破坏性变更：清洗仅影响新入库文档。
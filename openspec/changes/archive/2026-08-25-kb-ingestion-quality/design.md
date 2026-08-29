# kb-ingestion-quality Design

## Context

在 P0（混合检索+精排）与 P1（同义词+元数据+分领域库）基础上，补齐入库质量与可观测（详见 proposal.md）。

## Goals / Non-Goals

**Goals:**
- 解析后文本清洗去噪。
- 大文件上传异步处理，不阻塞请求线程。
- OCR 作为扫描件/图片型 PDF 的主路径前置；表格保留结构。
- 答案引用精确到 chunk/页码。
- 提供检索命中率评估脚本。

**Non-Goals:**
- 不改 P0/P1 的检索策略、元数据设计。
- 不引入完整 RAGAS 图形化平台，仅脚本级指标。

## Decisions

1. **异步用现有技术栈的轻量方案（线程池/后台任务）优先，Celery 仅在需要时引入。**
   - 理由：当前上传量级下线程池足够，避免额外队列运维；状态仍用 `kb_document.status` 跟踪。

2. **清洗作为 `document_parser` 解析后的独立纯函数 `clean_text()`。**
   - 理由：与解析、分块解耦，可单测；清洗规则面向 PDF 噪声（空白/页眉页脚/控制字符）。

3. **OCR 顺序调整为「检测到图片型 PDF/扫描件 → 先 OCR → 再解析」，保留表格结构用 `pdfplumber` 表格提取。**
   - 理由：相比当前「解析失败才 OCR」的兜底顺序，成功率与信息保真更高。

4. **评估脚本输出 JSON 指标（命中率/平均倒数排名），不依赖额外服务。**

## Risks / Trade-offs

- [异步处理引入状态机复杂度] → 复用现有 Document Status Tracking 状态字段，最小改动。
- [OCR 增加解析耗时] → 仅在检测到无文本层或图片型 PDF 时触发 OCR。

## Migration Plan

1. 新增 `clean_text()` 并接入解析链路。
2. 上传管线切异步 + 状态跟踪。
3. 调整 OCR 主路径与表格提取。
4. `chain.py` 增加 chunk 级引用。
5. 新增评估脚本。

## Open Questions

（无）
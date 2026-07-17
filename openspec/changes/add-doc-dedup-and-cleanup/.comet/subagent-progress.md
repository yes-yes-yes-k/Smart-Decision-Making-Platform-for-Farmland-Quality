# Subagent Progress Checkpoint

- Change: add-doc-dedup-and-cleanup
- review_mode: standard
- tdd_mode: tdd

## Task 1: Document 模型新增 file_hash 字段

- **状态**: done
- **阶段**: checkoff（协调者复核完成，跳过独立 reviewer）
- **实现提交**: 81b5e3305bede7746e644f201f176b485ec1f989
- **变更文件**: framework/models/document.py, tests/test_upload.py
- **RED 证据**: test_document_model_fields 和 test_document_to_dict 失败（file_hash 属性不存在 / to_dict 无 file_hash 键）
- **GREEN 证据**: 2 passed in 1.42s
- **风险信号**: 命中"数据或 schema 迁归"，但已被项目 Global Constraints 缓解（init_db.py 的 drop_all + create_all 处理 schema 变更，无需单独迁移脚本）
- **协调者复核**: diff 5 行新增，字段类型 String(64)/nullable=True 符合设计文档 2.1，to_dict 正确更新。spec compliance ✓，code quality ✓。决定不派发独立 reviewer（机械性字段添加，风险已缓解，最终轻量审查会覆盖）
- **审查-修复轮次**: 0（未派发 reviewer）

---

## Task 2: compute_file_hash 分块流式 SHA-256 函数

- **状态**: BLOCKED
- **提交哈希**: 无（未提交，等待协调者决策）
- **变更文件**（已改动未提交，保留在原地）:
  - framework/upload/file_upload.py（+11 行：`import hashlib` + `compute_file_hash` 函数，逐字按 brief Step 5 实现）
  - tests/test_upload.py（+57 行：3 个测试函数，逐字按 brief Step 1/2/3 实现）
- **RED 证据**: brief Step 4 命令输出 —— 3 个测试全部 FAILED，错误均为 `ImportError: cannot import name 'compute_file_hash' from 'framework.upload.file_upload'`（`3 failed in 0.96s`）
- **GREEN 证据**: brief Step 6 命令输出 —— `1 failed, 2 passed in 1.21s`
  - PASSED: test_compute_file_hash_empty_file, test_compute_file_hash_large_file_chunked
  - FAILED: test_compute_file_hash_small_file（AssertionError，哈希不匹配）
- **覆盖测试**: tests/test_upload.py::test_compute_file_hash_empty_file（通过）, ::test_compute_file_hash_small_file（失败）, ::test_compute_file_hash_large_file_chunked（通过）
- **Concerns**: **阻塞——brief 的 `test_compute_file_hash_small_file` 测试在 Windows 上存在换行符可移植性 bug，与 `compute_file_hash` 函数实现无关。**

  ### 根因（已用独立 Python 命令验证，100% 确认）
  测试代码 `with open(test_file, 'w', encoding='utf-8') as f: f.write(content)` 在 Windows 上以**文本模式**写入，Python 默认启用 universal newlines 翻译，把内存中的 `\n`（LF, 0x0A）翻译为磁盘上的 `\r\n`（CRLF, 0x0D 0x0A）。因此：
  - 磁盘文件实际字节 = `content` 中 `\n` 被替换为 `\r\n` 后的 UTF-8 字节
  - `compute_file_hash` 以 `'rb'` 二进制读这些字节并算 SHA-256，得到 `45d5e60cee25...688ff11b9e6d5`
  - 而 `expected = hashlib.sha256(content.encode('utf-8')).hexdigest()` 用的是含 `\n` 的原始内存字符串，得到 `af01776b5623...9175f8209da03`
  - 二者必然不一致。验证命令输出：`LF: af01776b...`（=expected），`CRLF: 45d5e60c...`（=result），与失败信息完全吻合。

  ### 关键判断
  - `compute_file_hash` 函数实现**完全正确**：它读字节、算 SHA-256，这是哈希函数的本职行为，不应“感知”换行符。空文件与大文件（纯 `A`，无换行）两个测试通过也佐证函数正确。
  - 该测试在 Linux/macOS 上会通过（文本模式不翻译 `\n`），brief 作者大概率在 Linux 环境验证过，未考虑 Windows。
  - 项目既有测试 `test_parse_txt` 用 `assert "..." in content`（子串断言）规避了同一问题；新测试用精确哈希等值断言，才暴露了换行符差异。

  ### 为什么不自行修复
  任务约束双重明确：（1）“严格按 brief 中的代码逐字实现，不要修改……测试断言值”；（2）“测试无法通过……返回 BLOCKED 状态……不要硬编码或绕过测试”。自行改测试写法（如 `open(..., 'wb')` 写字节，或加 `newline=''`）会同时违反“逐字”与“不绕过”两条。故按约束上报 BLOCKED，等待协调者授权。

  ### 给协调者的候选修复方案（需授权后执行，二选一）
  1. **改测试文件写法为二进制模式**（最小改动，推荐）：
     ```python
     with open(test_file, 'wb') as f:
         f.write(content.encode('utf-8'))
     ```
     同样改 `test_file2`。此改动不动函数、不动断言值，仅消除平台换行符翻译。
  2. **在测试中显式禁用换行翻译**：
     ```python
     with open(test_file, 'w', encoding='utf-8', newline='') as f:
         f.write(content)
     ```
     `newline=''` 关闭翻译，写入保持 `\n`。

  授权任一方案后，我可在 <1 分钟内完成改动、重跑测试、提交。当前两处改动（函数+测试）已保留在工作区未提交，方便协调者直接检查或继续。

### Task 2 Fix: Windows 换行符可移植性修复

- **状态**: DONE
- **提交哈希**: c2e834d
- **修复内容**: test_compute_file_hash_small_file 文件写入从 'w' 文本模式改为 'wb' 二进制模式，消除 Windows \n→\r\n 翻译
- **GREEN 证据**: 3 passed in 0.19s
- **Concerns**: 无

---

## Task 3: save_uploaded_file 返回三元组 + docs.py 解包适配

- **状态**: DONE
- **提交哈希**: 8949b1fd12e77f909dcef2005d36618508c00e5f
- **变更文件**:
  - framework/upload/file_upload.py（save_uploaded_file 返回三元组）
  - framework/api/routes/docs.py（upload_document 解包适配，第 31 行）
  - tests/test_upload.py（+test_save_uploaded_file_returns_triple）
- **RED 证据**: `python -m pytest tests/test_upload.py::test_save_uploaded_file_returns_triple -v` 输出 `1 failed in 1.18s`，关键失败信息：`ValueError: not enough values to unpack (expected 3, got 2)`（在 `new_filename, file_path, file_hash = save_uploaded_file(MockFile())` 处触发，当前 save_uploaded_file 只返回二元组）；测试因主断言失败后 finally 清理时残留文件导致二次 `OSError: [WinError 145] 目录不是空的`，根本原因是函数返回值 arity 不匹配，与预期 RED 表现一致。
- **GREEN 证据**: `python -m pytest tests/test_upload.py::test_save_uploaded_file_returns_triple -v` 输出 `1 passed in 0.15s`。
- **回归证据**: `python -m pytest tests/test_upload.py -v` 输出 `10 passed in 1.89s`（test_allowed_file, test_get_file_type, test_parse_txt, test_parse_md, test_document_model_fields, test_document_to_dict, test_compute_file_hash_empty_file, test_compute_file_hash_small_file, test_compute_file_hash_large_file_chunked, test_save_uploaded_file_returns_triple 全部通过）。
- **覆盖测试**: tests/test_upload.py::test_save_uploaded_file_returns_triple
- **Concerns**: 无（save_uploaded_file 在 file.save(file_path) 后调用 compute_file_hash 计算哈希，SHA-256 分块流式与 Task 2 一致；docs.py 仅解包适配，未引入查重逻辑，Document 构造未动，符合 Task 3 边界，查重与 file_hash 落库留待 Task 4）。

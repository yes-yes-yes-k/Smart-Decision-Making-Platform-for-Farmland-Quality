## ADDED Requirements

### Requirement: DataFile 数据文件模型
系统 SHALL 提供 `DataFile` SQLAlchemy 模型（位于 `framework/models/data_file.py`），对应数据库表 `kb_data_file`，用于存储用户上传的数据文件（raw_data/improved_data 分类）的元数据。`DataFile` 模型 SHALL 被 `framework/api/routes/docs.py` 导入，支持数据文件上传接口的存储和查询功能。

`DataFile` 模型 SHALL 包含以下字段：
- `id`：主键，自增整数
- `doc_name`：原始文件名（字符串）
- `file_path`：存储路径/新文件名（字符串）
- `file_type`：文件类型（字符串）
- `file_size`：文件大小，字节（整数）
- `category`：文件分类（字符串，如 raw_data/improved_data）
- `treatment_type`：治理类型（字符串，可选）
- `status`：状态标志（整数，如 1=有效）
- `create_by`：创建者用户 ID（整数）
- `create_time`：创建时间（datetime，默认当前时间）

`DataFile` 模型 SHALL 提供 `to_dict()` 方法，返回包含上述字段的字典。

#### Scenario: 数据文件上传存储
- **WHEN** 用户上传一个分类为 `raw_data` 的数据文件，且文件通过查重检查
- **THEN** 系统 SHALL 创建 `DataFile` 实例，填充 doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by 字段
- **AND** 系统 SHALL 将实例添加到数据库会话并提交
- **AND** 系统 SHALL 返回包含 `data_file.to_dict()` 的成功响应

#### Scenario: DataFile 模型导入可用
- **WHEN** `framework/api/routes/docs.py` 执行 `from framework.models.data_file import DataFile`
- **THEN** 导入 SHALL 成功，不抛出 ModuleNotFoundError
- **AND** `DataFile` SHALL 可用于构造数据文件实例

#### Scenario: to_dict 方法返回完整字段
- **WHEN** 调用 `DataFile` 实例的 `to_dict()` 方法
- **THEN** 返回的字典 SHALL 包含 id/doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by/create_time 字段

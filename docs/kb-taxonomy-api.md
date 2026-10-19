# 公共知识与多标签分类 API

所有接口均使用 JWT。领域代码固定为：

- `heavy_metal`
- `food_security`
- `cultivated_land_quality`

## 上传

`POST /api/v1/docs/upload` 使用 `multipart/form-data`：

- `file`：文件
- `visibility_scope`：`private` 或 `public`；只有管理员可发布公共知识
- `domain_labels`：必填；只接受三个一级领域代码。支持 JSON 数组、逗号分隔字符串或重复表单字段
- `category`：保留的物理存储分组字段，用于兼容旧客户端；不再自动生成或授予领域标签

入库只保存 `domain_labels` 中明确指定的领域。系统不会扫描文档正文生成一级或二级候选标签，也不会产生新的待人工审核记录。

用户上传的私有知识只对本人可见。检索权限恒为“公共知识或本人私有知识”。

## 查询分类体系

`GET /api/v1/docs/taxonomy`

返回三个一级领域及其二级主题标签。

## 标签维护

入库不再自动产生审核候选。以下管理员接口保留用于查询历史记录和人工纠正标签：

`GET /api/v1/docs/label-reviews?status=pending&level=domain`

- `status`：`pending`、`approved`、`rejected`
- `level`：`domain`、`topic`、`all`
- 默认只返回一级领域候选，避免二级主题淹没交叉领域审核队列

`PUT /api/v1/docs/{document_id}/labels`

```json
{
  "approved_labels": ["heavy_metal"],
  "rejected_labels": ["food_security"]
}
```

人工修改后会同步更新该文档全部向量分块的领域元数据。

## 数据迁移

迁移脚本默认只创建结构，不修改历史资料。当前确认方案使用：

```powershell
python scripts/migrate_kb_taxonomy.py `
  --publish-existing `
  --approve-domain cultivated_land_quality `
  --propose-labels `
  --sync-vectors
```

重新运行自动分类规则时，可增加 `--refresh-proposals`。人工通过或驳回的结果不会被自动刷新覆盖。

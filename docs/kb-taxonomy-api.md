# 公共知识与多标签分类 API

所有接口均使用 JWT。领域代码固定为：

- `heavy_metal`
- `food_security`
- `cultivated_land_quality`

## 上传

`POST /api/v1/docs/upload` 使用 `multipart/form-data`：

- `file`：文件
- `visibility_scope`：`private` 或 `public`；只有管理员可发布公共知识
- `domain_labels`：JSON 数组、逗号分隔字符串或重复表单字段
- `category`：保留的主分类字段，用于兼容旧客户端

用户上传的私有知识只对本人可见。检索权限恒为“公共知识或本人私有知识”。

## 查询分类体系

`GET /api/v1/docs/taxonomy`

返回三个一级领域及其二级主题标签。

## 人工审核

只有管理员可访问审核接口。

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

审核通过后会同步更新该文档全部向量分块的领域元数据；待审核标签不参与领域检索。

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

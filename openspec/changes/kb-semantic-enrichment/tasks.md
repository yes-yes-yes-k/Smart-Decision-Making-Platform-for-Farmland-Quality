## 1. 同义词/专业词表

- [x] 1.1 新增耕地领域同义词词表 `soil_synonyms.json`
- [x] 1.2 实现同义词词表加载与查询替换函数
- [x] 1.3 在 `framework/rag/chain.py` 检索前接入查询预处理
- [x] 1.4 为同义词替换编写单元测试（命中替换、未命中原样通过）

## 2. chunk 元数据增强

- [x] 2.1 扩展 `chroma_store` 元数据写入，支持 chunk 级字段
- [x] 2.2 更新 `docs.py` 入库时计算并写入 category/treatment_type/chunk_index（page/section 本阶段不写入，留后续）
- [x] 2.3 为元数据写入编写测试

## 3. 分领域 collection

- [x] 3.1 扩展 `chroma_store` 支持按 category 路由到分领域 collection
- [ ] 3.2 提供 collection 重建脚本，按 category 迁移现有文档
- [x] 3.3 为领域路由与回退逻辑编写测试

## 4. 验证与回归

- [ ] 4.1 运行完整测试套件，确保 P0 + P1 改动无回归
- [ ] 4.2 端到端验证同义词替换与分领域路由生效
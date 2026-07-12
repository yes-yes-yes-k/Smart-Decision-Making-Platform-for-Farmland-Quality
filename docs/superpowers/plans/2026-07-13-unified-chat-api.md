---
change: migrate-and-unify-framework
design-doc: docs/superpowers/specs/2026-07-12-migrate-and-unify-framework-design.md
base-ref: cfb602ac8b3aa8bf698945eb862898bac5f910ef
---

# 统一聊天接口与智能路由实施计划

**Goal:** 将 `/api/v1/models/run` 接口改造为智能路由模式，并合并 `/api/v1/chat/` 聊天接口，形成统一的智能问答入口。

---

### Task 1: 在多智能体状态中新增 RAG 相关字段

- [x] **Step 1: 更新状态定义**
- [x] **Step 2: 测试状态定义**
- [x] **Step 3: Commit**

---

### Task 2: 实现 RAG 节点函数

- [x] **Step 1: 编写 RAG 节点函数**
- [x] **Step 2: 更新路由函数**
- [x] **Step 3: 更新聚合函数**
- [x] **Step 4: 测试节点函数**
- [x] **Step 5: Commit**

---

### Task 3: 更新多智能体编排器图

- [x] **Step 1: 更新图构建**
- [x] **Step 2: 更新 run 方法**
- [x] **Step 3: 测试编排器**
- [x] **Step 4: Commit**

---

### Task 4: 合并聊天和模型接口

- [x] **Step 1: 重构 chat 路由的 POST / 端点**
- [x] **Step 2: 简化 models 路由**
- [x] **Step 3: 更新 app.py 中的蓝图注册**
- [x] **Step 4: 测试合并后的接口**
- [x] **Step 5: Commit**

---

### Task 5: 更新 OpenSpec tasks.md

- [x] **Step 1: 勾选已完成的任务**
- [x] **Step 2: 新增智能路由合并任务**
- [x] **Step 3: Commit**

---

## 计划完成

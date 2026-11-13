# 第 1 阶段验收

2026-11-10：调研、基线、契约交付通过；不代表通量业务或绘图测试已通过。阶段2–5尚未开始。

## 环境与测试（1.1）

使用项目根 `.venv/Scripts/python.exe`，Python3.12、PostgreSQL17.4、pytest9.1.1、psycopg2-binary2.9.12。matplotlib/rasterio/seaborn缺失。

- `python -m pytest tests/test_cd_conversation.py tests/test_cd_trial.py -q --tb=short`：11 passed。
- `python -m pytest tests/test_cd_flux.py tests/test_heavy_metal_cd_visualization.py tests/test_cd_conversation.py tests/test_cd_trial.py -q --tb=short`：收集因缺matplotlib中断，1 error。
- `python -m pytest tests/test_cd_flux.py -q --tb=short`：11个setup errors，均因fixture导入缺matplotlib。未证明通量测试通过。

本阶段记录真实失败基线；阶段2准备环境后需重跑。

## 只读审计（1.2）

`scripts/audit_cd_chat_stage1.py` 使用数据库只读事务，只输出本地JSON，不输出密码。运行参数 `--env-file <项目根>/.env --database <库名> --output artifacts/cd-chat-stage1/<报告>.json`。

恢复库 `db_enterprise_qa_cd_20261103`：地块45588，快照16464；两类预测各40100，重复地块/样点键0。移植映射40100，19乡镇；缺失地块/启用乡镇均0。试算表0行，flux输入/输出表不存在。

默认库 `db_enterprise_qa`：地块5488、快照16464，没有Cd预测/移植映射、flux和独立试算表。后续必须明确选库。

区域目录1687行；恢复库启用省1、市1、县10、乡镇103、村1199、zone373。启用节点缺失父节点、停用父节点、循环、行政父类型异常均0。自有面积映射30751行：省/市各5488，县5600行覆盖5488地块，乡镇6057行覆盖5488地块，村8118行覆盖5483地块。缺失地块0。跨界多行不等于样点重复，聚合必须采用现有最大面积归属并去重。

报告：`artifacts/cd-chat-stage1/restored-audit.json`、`default-audit.json`。审计不证明几何有效、单位核验或全行政区覆盖。

## 年度/企业证据（1.3）

现有预测表无业务年度，代码flux模型无年度及企业字段，两库无flux表。年度、企业输入没有可用真实记录；土壤快照年度和导入时间不能代替通量年度。新版需提供明确年度、来源依据及已换算企业通量；历史未知保留，不填零。

## 单位复算（1.4）

推导和证据见stage-1-contract.md。独立Decimal运算验证土壤质量2600000 kg/ha，末期浓度0.2346153846153846 mg/kg，六位小数0.234615。没有调用原计算函数。旧公式在20cm、一年及约定容重单位下数值成立，常数命名不准确；历史容重原始单位仍未核验，不自动升级可信状态。

## 契约与验收结论（1.5）

stage-1-contract.md和stage-1-schema.sql固定并行v2表、年度/来源/未知键唯一性、企业空值、输入修订、公式版本、legacy CSV及回滚规则。DDL仅评审，未执行；约束、迁移幂等和恢复测试属于阶段2。

前置限制已明确：补绘图依赖并重跑基线、开发v2迁移、核验输入单位、修复来源筛选和聚合。完整八项及明确单位/厚度满足后才开放新版浓度。当前无真实企业年度数据，不能宣称业务可答。完成的是阶段1调查与契约，不代勾后续任务。

# PostgreSQL 三地块综合诊断报告

生成时间：2026-09-02T02:32:12.901695+00:00
权威数据源：PostgreSQL `db_enterprise_qa.public.parcel_info`。

## 执行流程

Coordinator → TrafficGate → InputResolver → PlanValidator → Wave 1（model-2/3）→ TriggerEvaluator → Wave 2（model-4/5）→ EvidenceResearcher → Reporter → Release

## 地块 4190

数据版本：2026-08-18 22:17:29.063180+08:00。土地类型：upland；肥料类型：compound；目标 pH：6.5。
输入快照：pH 5.42084；有机质 31.266078；全氮 1.4055；有效磷 46.235236；速效钾 56.937799。

- model-2 质量评价（ok）：等级 3，综合指数 0.8339658156201359。
- model-3 障碍诊断（ok）：多障碍；主要因素 ['YXL', 'DXBW']；次要因素 ['SXJ', 'GGNL']。
- model-4 酸化改良（ok）：YTK 5047.648922980647；MBNT 11671.284053654765。
- model-5 有机质培肥（ok）：预测施用量 223.74515187615359。

节点状态：Coordinator[comprehensive_analysis] → TrafficGate[comprehensive] → InputResolver[resolved] → PlanValidator[approved] → Wave1[done] → TriggerEvaluator[done] → Wave2[done] → EvidenceResearcher[postgres_snapshot_bound] → Reporter[drafted] → Release[released]

## 地块 1

数据版本：2026-08-18 22:17:26.231302+08:00。土地类型：upland；肥料类型：compound；目标 pH：6.5。
输入快照：pH 5.313572；有机质 29.341281；全氮 1.4055；有效磷 35.477797；速效钾 45.48295。

- model-2 质量评价（ok）：等级 2，综合指数 0.843636751626378。
- model-3 障碍诊断（ok）：多障碍；主要因素 ['SXJ', 'DXBW']；次要因素 ['GGNL', 'SJD', 'PSNL']。
- model-4 酸化改良（ok）：YTK 5047.921846363748；MBNT 11671.284053654765。
- model-5 有机质培肥（ok）：预测施用量 223.74515187615359。

节点状态：Coordinator[comprehensive_analysis] → TrafficGate[comprehensive] → InputResolver[resolved] → PlanValidator[approved] → Wave1[done] → TriggerEvaluator[done] → Wave2[done] → EvidenceResearcher[postgres_snapshot_bound] → Reporter[drafted] → Release[released]

## 地块 1593

数据版本：2026-08-18 22:17:27.457983+08:00。土地类型：upland；肥料类型：compound；目标 pH：6.5。
输入快照：pH 5.10864；有机质 21.128646；全氮 1.4055；有效磷 38.120621；速效钾 59.84513。

- model-2 质量评价（ok）：等级 5，综合指数 0.7678844802687327。
- model-3 障碍诊断（ok）：多障碍；主要因素 ['DXBW']；次要因素 ['ZDGX', 'SXJ', 'YJZ', 'SJD', 'GGNL']。
- model-4 酸化改良（ok）：YTK 5048.673813328237；MBNT 11671.284053654765。
- model-5 有机质培肥（ok）：预测施用量 339.60920628784805。

节点状态：Coordinator[comprehensive_analysis] → TrafficGate[comprehensive] → InputResolver[resolved] → PlanValidator[approved] → Wave1[done] → TriggerEvaluator[done] → Wave2[done] → EvidenceResearcher[postgres_snapshot_bound] → Reporter[drafted] → Release[released]

## 限制与解释

本报告使用 PostgreSQL 权威地块快照和项目当前正式模型生成。`model_execution_log` 的溯源列与 trace 索引已迁移，本次四个模型结果均成功持久化。YTK、MBNT 和培肥预测量的单位应以模型数据字典为准，本报告不推断未声明单位。结果用于工程验证，生产处方仍需现场采样与农艺师复核。

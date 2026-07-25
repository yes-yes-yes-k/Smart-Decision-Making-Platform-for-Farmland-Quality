## 1. 修复 parse_output 解析逻辑

- [x] 1.1 修复 parse_output 函数：修正 section 标记识别（匹配 '地块代码'/'原始指标值'/'耕地质量综合指数'/'障碍度因子' 等实际关键词）、parcel_info 解析（中文冒号 '：' 分隔）、indicators 解析（正则匹配 '指标名(代码): 值'）、composite 解析（提取综合指数 float 和质量等级字符串）、obstacle_degree 解析（正则匹配 '指标名 : 障碍度值 障碍类型'，rank 按顺序生成，新增 level 字段）

## 2. 测试验证

- [x] 2.1 编写单元测试：使用捕获的真实 exe 输出样本（A0001 地块）验证 parse_output 各字段解析正确，覆盖空输出/格式异常等边界场景
- [x] 2.2 端到端验证与回归测试：运行 runner.run('A0001') 确认 status=ok 且所有字段非空，运行 farmland_grade_eval 模块全部测试确认无回归

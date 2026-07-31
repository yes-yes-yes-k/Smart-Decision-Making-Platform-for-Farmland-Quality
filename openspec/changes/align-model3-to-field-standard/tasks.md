## 1. 配置层字段标准化（config.py）

- [ ] 1.1 更新 COEFFICIENTS 字典：将指标键名从 PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH 改为 SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD
- [ ] 1.2 更新 WEIGHTS 字典：将指标键名同步改为标准命名
- [ ] 1.3 更新 COLUMN_RENAME：将映射从 `一级农业区→JY`/`二级农业区→EJ` 改为 `YJNYQ→YJNYQ`/`EJNYQ→EJNYQ`（即直接使用标准列名，移除中文列名映射）
- [ ] 1.4 更新 TEXT_VALUE_MAPS：将键名从 DX/GZ/ZD/GG/PS 改为 DXBW/GCZD/ZDGX/GGNL/PSNL
- [ ] 1.5 更新 INDICATOR_NAME_MAP：将键名从 PH/YJ/etc. 改为 SJD/YJZ/etc.，值保持中文显示名
- [ ] 1.6 更新 calc_obstacle_level 函数：将所有指标引用从 PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH 改为标准命名，隶属度引用从 xxx_LD 改为 xxxLSD

## 2. 评价逻辑标准化（evaluation.py）

- [ ] 2.1 更新 evaluate_single：将 continuous_cols/discrete_cols/weighted_indicators 列表改为标准命名，隶属度后缀从 _LD 改为 LSD，障碍度后缀从 _OD 改为 ZAD
- [ ] 2.2 更新 evaluate_single：将 composite_weight 改为 ZHQZ，grade 改为 GDZLDJ
- [ ] 2.3 更新 evaluate_single：障碍等级列名从 `INDICATOR_NAME_MAP[ind]+'障碍等级'` 改为 `ind+'ZADJ'`（使用标准指标代码+ZADJ后缀）
- [ ] 2.4 新增障碍诊断输出：在 evaluate_single 中集成 diagnosis_row 逻辑，生成 ZALX/ZYZAYS/CYZAYS 字段
- [ ] 2.5 更新 bulk_evaluate：将 required 列表从 JY/EJ/PH/etc. 改为 YJNYQ/EJNYQ/SJD/etc.，区域映射字段从 JY 改为 YJNYQ
- [ ] 2.6 更新 bulk_evaluate：移除 COLUMN_RENAME 中的中文列名映射依赖，直接使用 YJNYQ/EJNYQ 标准列名

## 3. 诊断逻辑标准化（diagnosis.py）

- [ ] 3.1 更新 diagnosis_row：将 _OD 后缀改为 ZAD，`障碍等级` 改为 ZADJ 后缀匹配逻辑
- [ ] 3.2 更新 diagnosis_row：对齐 V2.0 的 replace_abbr_in_text 逻辑，使用 INDICATOR_DISPLAY_MAP 将缩写替换为中文显示名
- [ ] 3.3 更新 diagnose 函数：将 weighted_indicators 列表改为标准命名，字段引用从 _OD 改为 ZAD
- [ ] 3.4 更新 diagnose 函数：障碍等级引用从 `INDICATOR_NAME_MAP[ind]+'障碍等级'` 改为 `ind+'ZADJ'`
- [ ] 3.5 更新 query_parcel：确保返回的 evaluation 和 diagnosis 数据使用标准字段名

## 4. 存储层标准化（storage.py）

- [ ] 4.1 更新 create_tables：将 evaluation_results 表列名从 PH/YJ/etc. 改为 SJD/YJZ/etc.，隶属度列从 xxx_LD 改为 xxxLSD
- [ ] 4.2 更新 create_tables：将 composite_weight 改为 ZHQZ，grade 改为 GDZLDJ
- [ ] 4.3 更新 create_tables：将 diagnosis_results 表的障碍等级列从 `xxx_obstacle_level` 改为 `xxxZADJ`，障碍度列从 `xxx_obstacle_degree` 改为 `xxxZAD`
- [ ] 4.4 更新 create_tables：在 diagnosis_results 表中新增 ZALX/ZYZAYS/CYZAYS 列
- [ ] 4.5 更新 save_evaluation：将所有字段引用改为标准命名
- [ ] 4.6 更新 save_diagnosis：将所有字段引用改为标准命名，新增 ZALX/ZYZAYS/CYZAYS 字段存储
- [ ] 4.7 删除旧数据库文件（farmland_diagnosis.db），确保表结构重建

## 5. 消费端更新（problem_agent.py）

- [ ] 5.1 更新 answer_question：将 evaluation.get("grade") 改为 evaluation.get("GDZLDJ")
- [ ] 5.2 更新 answer_question：将 diagnosis.get("obstacle_type") 改为 diagnosis.get("ZALX")，main_factors 改为 ZYZAYS，secondary_factors 改为 CYZAYS
- [ ] 5.3 在 agent 响应中暴露 ZALX/ZYZAYS/CYZAYS 字段

## 6. 模块导出更新（__init__.py）

- [ ] 6.1 更新 __init__.py 导出列表，确保新增的障碍诊断函数和配置正确导出

## 7. 测试更新（tests/test_farmland_diagnosis.py）

- [ ] 7.1 更新 test_region_map/test_coefficients_exists/test_weights_exists/test_indicator_name_map：将字段引用改为标准命名
- [ ] 7.2 更新 test_calc_obstacle_level_* 测试：将 row 字典键名从 PH/YJ/SXK 改为 SJD/YJZ/SXJ
- [ ] 7.3 更新 test_storage_* 测试：将 record 字典字段名改为标准命名（SJD/YJZ/etc.，xxxLSD，ZHQZ，GDZLDJ）
- [ ] 7.4 更新 test_evaluate_single/test_bulk_evaluate：将输入数据和断言字段改为标准命名
- [ ] 7.5 更新 test_diagnosis_row_* 测试：将 _OD 后缀改为 ZAD，障碍等级改为 ZADJ
- [ ] 7.6 更新 test_diagnose_flow：验证 ZALX/ZYZAYS/CYZAYS 输出
- [ ] 7.7 新增测试：验证障碍度不覆盖原始指标值（ZAD 列独立于原始值）

## 8. 文档纳入

- [ ] 8.1 确认 docs/model-integration-analysis.md 和 docs/model-provider-spec.md 纳入版本控制

## 9. 验证

- [ ] 9.1 运行 tests/test_farmland_diagnosis.py 全部测试通过
- [ ] 9.2 运行项目整体测试套件确认无回归
- [ ] 9.3 验证标准测试数据输入后输出字段名符合 Excel 规范

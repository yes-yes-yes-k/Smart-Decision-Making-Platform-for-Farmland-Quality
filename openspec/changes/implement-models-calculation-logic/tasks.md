## 实现任务

### 共享基础设施

- [ ] 1. 创建 `framework/domain/calculations/coefficients.py`：移植 Model-2/3 的隶属度系数（4 个二级农业区的 a/c/ut1/ut2、概念型隶属度表、权重表、等级阈值），移植 Model-3 的障碍等级阈值和 DISCRETE_CN_MAP
- [ ] 2. 更新 `ParcelDataAccessor._map_indicators_to_inputs`：实现 V3.0 英文 snake_case → 各模型输入字段的统一映射（soil_ph→SJD/pH, organic_matter→YJZ/SOMbe 等），离散指标中文值转代码
- [ ] 3. 确认 `soil_indicators` JSON 的 12 个指标字段名与 V3.0 设计文档一致，补充缺失的字段名映射（bulk_density→TRRZ, topsoil_thickness→YXTCHD, plow_layer_thickness→GCHD）

### Model-2 质量等级评价

- [ ] 4. 创建 `framework/domain/calculations/grade_calculation.py`：实现 `membership_numeric()` 峰型/戒上型隶属度函数，`evaluate_land_quality()` 12 指标加权和 + 等级判定
- [ ] 5. 更新 `framework/agents/specialized/grade_agent.py`：在 execute 中调用 grade_calculation，替代占位实现，确保 quality_grade 和 quality_index 非零
- [ ] 6. 编写 Model-2 计算单元测试：验证峰型隶属度、戒上型隶属度、加权和、等级判定

### Model-3 障碍诊断

- [ ] 7. 创建 `framework/domain/calculations/obstacle_calculation.py`：实现 `calc_continuous()`、`calc_discrete()` 隶属度，`calc_obstacle_level()` 障碍等级判定，障碍度计算 `(1-membership)*weight/sum`，`diagnosis_row()` 主要/次要因子识别
- [ ] 8. 更新 `framework/agents/specialized/problem_agent.py`：在 execute 中调用 obstacle_calculation，替代 obstacle_type=未知 占位实现
- [ ] 9. 编写 Model-3 计算单元测试：验证障碍等级判定（pH/有机质/磷/钾等阈值）、障碍度计算、诊断结果

### Model-4 酸化改良

- [ ] 10. 创建 `framework/domain/calculations/acidification_calculation.py`：移植 4 个产酸平衡函数（paddy_urea、paddy_compound、upland_urea、upland_compound），计算 YTK（石灰施用量）和 MBNT（有机肥施用量）
- [ ] 11. 更新 `framework/agents/specialized/acidification_agent.py`：调用 acidification_calculation 替代外部 .exe 模型，确保 status 不再为 rejected
- [ ] 12. 编写 Model-4 计算单元测试：验证 4 个函数的产酸平衡计算（Adep/Acrop/ANcy/Aagri/Aback/YTK/MBNT）

### Model-5 有机质培肥

- [ ] 13. 从原始 Jupyter notebook 导出 RF 模型为 `.joblib` 文件，放置在 `data/model_artifacts/`（旱地 upland_dose_rf.joblib、水田 paddy_dose_rf.joblib）
- [ ] 14. 创建 `framework/domain/calculations/organic_matter_calculation.py`：实现延迟加载 RF 模型、特征映射、Dose 预测，scikit-learn 不可用时降级到规则
- [ ] 15. 更新 `framework/agents/specialized/organic_matter_agent.py`：调用 organic_matter_calculation 替代简单规则，RF 可用时 simulated=False
- [ ] 16. 编写 Model-5 计算单元测试：验证 RF 模型加载、特征映射、Dose 预测、降级路径

### Model-1 稳定性风险评价

- [ ] 17. 创建 `framework/domain/calculations/stability_calculation.py`：移植 3 个核心模块（calculate_boundary_safety、calculate_support_balance、calculate_key_criticality），从 DB 读取替代 Shapefile
- [ ] 18. 更新 `framework/agents/specialized/stability_agent.py`：调用 stability_calculation 替代 LLM 降级路径，确保 status=ok、data_source=db
- [ ] 19. 编写 Model-1 计算单元测试：验证边界安全度、支撑均衡度、关键指标临界度计算

### 集成验证

- [ ] 20. 运行完整测试套件确认无回归
- [ ] 21. 使用验证脚本 `scripts/verify_thematic_models_db.py` 重新验证 5 个模型 x 3 个地块的计算流程，确认全部 status=ok、data_source=db、持久化成功

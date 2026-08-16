"""V3.0 专题模型 ORM 结构验证测试。

验证 framework/models/thematic_model.py 中 15 个 ORM 模型类的结构：
- 模型类可导入
- 表名与 V3.0 §3 列表一致
- 列数与 DDL 脚本一致
- 10 个 FK 约束存在
- 索引名按表前缀化
"""
import os
import re
import unittest

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

import framework.models.thematic_model as thematic_model


# V3.0 §3 表名列表（15 张表，按 DDL 创建顺序）
EXPECTED_TABLES = [
    "thematic_model_registry",
    "spatial_data_layer",
    "model_execution_log",
    "parcel_geometry",
    "stability_risk_result",
    "quality_grade_result",
    "obstacle_diagnosis_result",
    "acidification_remediation_result",
    "organic_matter_result",
    "comprehensive_fertility_result",
    "routing_decision_log",
    "model_evaluation_metrics",
    "exclusive_rule_config",
    "parcel_info",
    "model_version_history",
]

# 模型类名（与 EXPECTED_TABLES 按相同顺序排列）
EXPECTED_MODELS = [
    "ThematicModelRegistry",
    "SpatialDataLayer",
    "ModelExecutionLog",
    "ParcelGeometry",
    "StabilityRiskResult",
    "QualityGradeResult",
    "ObstacleDiagnosisResult",
    "AcidificationRemediationResult",
    "OrganicMatterResult",
    "ComprehensiveFertilityResult",
    "RoutingDecisionLog",
    "ModelEvaluationMetrics",
    "ExclusiveRuleConfig",
    "ParcelInfo",
    "ModelVersionHistory",
]

# 10 个 FK 约束名（来自 DDL，格式 fk_<table>_<column>）
EXPECTED_FK_CONSTRAINTS = [
    "fk_model_execution_log_agent_id",
    "fk_model_execution_log_layer_id",
    "fk_parcel_geometry_layer_id",
    "fk_stability_risk_result_execution_id",
    "fk_quality_grade_result_execution_id",
    "fk_obstacle_diagnosis_result_execution_id",
    "fk_acidification_remediation_result_execution_id",
    "fk_organic_matter_result_execution_id",
    "fk_comprehensive_fertility_result_execution_id",
    "fk_model_version_history_agent_id",
]

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DDL_PATH = os.path.join(_PROJECT_ROOT, "scripts", "thematic_models_v3_ddl.sql")


def _parse_ddl_column_counts(ddl_path):
    """从 DDL 脚本解析每张表的列数（排除 PRIMARY KEY / CONSTRAINT 行）。"""
    with open(ddl_path, encoding="utf-8") as f:
        content = f.read()

    counts = {}
    pattern = re.compile(r"CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*;", re.DOTALL)
    for match in pattern.finditer(content):
        table_name = match.group(1)
        body = match.group(2)
        col_count = 0
        for line in body.strip().splitlines():
            stripped = line.strip().rstrip(",")
            if not stripped:
                continue
            upper = stripped.upper()
            if upper.startswith("PRIMARY KEY"):
                continue
            if upper.startswith("CONSTRAINT"):
                continue
            col_count += 1
        counts[table_name] = col_count
    return counts


class ThematicModelOrmStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = thematic_model
        cls.ddl_column_counts = _parse_ddl_column_counts(_DDL_PATH)

    def _get_model(self, class_name):
        return getattr(self.models, class_name)

    # ------------------------------------------------------------------
    # 测试 1：15 个模型类可导入
    # ------------------------------------------------------------------
    def test_15_model_classes_importable(self):
        """测试 15 个模型类可导入且为 db.Model 子类。"""
        from framework.models.user import db

        self.assertEqual(len(EXPECTED_MODELS), 15)
        for name in EXPECTED_MODELS:
            self.assertTrue(
                hasattr(self.models, name),
                f"模型类 {name} 不在 thematic_model 模块中",
            )
            model_cls = self._get_model(name)
            self.assertTrue(
                issubclass(model_cls, db.Model),
                f"{name} 不是 db.Model 子类",
            )

    # ------------------------------------------------------------------
    # 测试 2：表名与 V3.0 §3 列表一致
    # ------------------------------------------------------------------
    def test_table_names_match_v3_list(self):
        """测试 15 张表名与 V3.0 §3 列表完全一致。"""
        actual_tables = {
            self._get_model(name).__tablename__ for name in EXPECTED_MODELS
        }
        expected = set(EXPECTED_TABLES)
        self.assertEqual(len(expected), 15)
        self.assertEqual(
            actual_tables,
            expected,
            f"表名不匹配: 缺少 {expected - actual_tables}, "
            f"多余 {actual_tables - expected}",
        )

    # ------------------------------------------------------------------
    # 测试 3：列数与 DDL 一致
    # ------------------------------------------------------------------
    def test_column_counts_match_ddl(self):
        """测试每个模型类的列数与 DDL 脚本中的列数一致。"""
        for class_name, table_name in zip(EXPECTED_MODELS, EXPECTED_TABLES):
            model_cls = self._get_model(class_name)
            orm_col_count = len(model_cls.__table__.columns)
            ddl_col_count = self.ddl_column_counts.get(table_name)
            self.assertIsNotNone(
                ddl_col_count,
                f"DDL 中未找到表 {table_name}",
            )
            self.assertEqual(
                orm_col_count,
                ddl_col_count,
                f"表 {table_name}: ORM 列数 {orm_col_count} "
                f"!= DDL 列数 {ddl_col_count}",
            )

    # ------------------------------------------------------------------
    # 测试 4：10 个 FK 约束存在
    # ------------------------------------------------------------------
    def test_10_fk_constraints_exist(self):
        """测试 10 个 FK 约束存在且名称符合 fk_<table>_<column> 格式。"""
        all_fk_names = set()
        total_fk_count = 0
        for class_name in EXPECTED_MODELS:
            model_cls = self._get_model(class_name)
            table = model_cls.__table__
            for constraint in table.constraints:
                if isinstance(constraint, ForeignKeyConstraint):
                    total_fk_count += 1
                    if constraint.name:
                        all_fk_names.add(constraint.name)

        self.assertEqual(
            total_fk_count,
            10,
            f"FK 约束总数 {total_fk_count} != 10",
        )
        expected_fks = set(EXPECTED_FK_CONSTRAINTS)
        self.assertEqual(
            all_fk_names,
            expected_fks,
            f"FK 约束名不匹配: 缺少 {expected_fks - all_fk_names}, "
            f"多余 {all_fk_names - expected_fks}",
        )

    # ------------------------------------------------------------------
    # 测试 5：索引名按表前缀化
    # ------------------------------------------------------------------
    def test_index_names_table_prefixed(self):
        """测试所有 UniqueConstraint 和 Index 名称按表前缀化。

        约束名应以 uk_<table>_ 或 idx_<table>_ 开头。
        """
        for class_name, table_name in zip(EXPECTED_MODELS, EXPECTED_TABLES):
            model_cls = self._get_model(class_name)
            table = model_cls.__table__

            named_items = []
            # 检查 UniqueConstraint 名称
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint) and constraint.name:
                    named_items.append(constraint.name)
            # 检查 Index 名称
            for index in table.indexes:
                if index.name:
                    named_items.append(index.name)

            for item_name in named_items:
                prefix_ok = (
                    item_name.startswith(f"uk_{table_name}_")
                    or item_name.startswith(f"idx_{table_name}_")
                )
                self.assertTrue(
                    prefix_ok,
                    f"表 {table_name} 的索引/约束名 '{item_name}' "
                    f"未按表前缀化（应以 uk_{table_name}_ 或 "
                    f"idx_{table_name}_ 开头）",
                )


if __name__ == "__main__":
    unittest.main()

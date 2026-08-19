"""混淆矩阵评估结果落库测试（PostgreSQL 测试库）。

覆盖两条路径：
1. write_metrics_to_db 落库（查询 ModelEvaluationMetrics 逐字段验证）
2. DB 失败保留 JSON 输出（commit 抛异常时不传播、告警发出、JSON 仍写入、DB 无记录）

PG 不可用时整个文件跳过（conftest.PG_AVAILABLE 控制）。
"""
import sys
import os
import json
import warnings

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "scripts"))
from tests.conftest import PG_AVAILABLE

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 测试库不可用")

# PG 不可用时跳过 thematic_model 相关导入（geoalchemy2 缺失会导致名字未定义）
if PG_AVAILABLE:
    from framework.api.app import create_app  # noqa: E402
    from framework.models.user import db  # noqa: E402
    from framework.models import ModelEvaluationMetrics  # noqa: E402
    from run_routing_regression import main, write_metrics_to_db  # noqa: E402


@pytest.fixture
def pg_app():
    """真实 PG 测试库 app context，前后清理 model_evaluation_metrics 表。"""
    app = create_app("default")
    with app.app_context():
        db.session.query(ModelEvaluationMetrics).delete()
        db.session.commit()
        yield app
        db.session.query(ModelEvaluationMetrics).delete()
        db.session.commit()


class TestRegressionMetricsDb:
    def test_metrics_written_to_db(self, pg_app):
        """write_metrics_to_db 落库：小 matrix 调用后逐字段验证 ModelEvaluationMetrics 记录。"""
        matrix = {
            "model-3-vs-model-2": {
                "tp": 10, "fp": 1, "fn": 2, "tn": 7,
                "total": 20, "accuracy": 0.85, "confusion_rate": 0.15,
            },
        }
        write_metrics_to_db(matrix, evaluation_mode="keyword")

        rows = db.session.query(ModelEvaluationMetrics).all()
        assert len(rows) == 1
        r = rows[0]
        assert r.model_pair == "model-3-vs-model-2"
        assert r.positive_label == "model-3"
        assert (r.tp, r.fp, r.fn, r.tn) == (10, 1, 2, 7)
        assert r.total == 20
        assert r.accuracy == 0.85
        assert r.confusion_rate == 0.15
        assert r.evaluation_mode == "keyword"
        assert r.sample_count == 20

    def test_db_failure_keeps_json(self, pg_app, monkeypatch, tmp_path):
        """DB 失败回退：commit 抛异常时 main() 不抛出、告警发出、JSON 仍输出、DB 无记录。"""
        def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(db.session, "commit", _boom)

        output = tmp_path / "confusion_matrix.json"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # 不应抛出：DB 异常被 write_metrics_to_db 隔离
            exit_code = main(["--output", str(output)])
        assert any("model_evaluation_metrics DB 写入失败" in str(w.message) for w in caught)

        # JSON 文件仍输出（降级备份）
        assert output.exists()
        matrix = json.loads(output.read_text(encoding="utf-8"))
        assert set(matrix.keys()) == {"model-3-vs-model-2", "model-4-vs-model-5"}

        # 退出码不被 DB 异常污染（0=达成, 1=未达成，取决于混淆率）
        assert exit_code in (0, 1)

        # DB 无记录（rollback 已在 write_metrics_to_db 内执行）
        rows = db.session.query(ModelEvaluationMetrics).all()
        assert len(rows) == 0

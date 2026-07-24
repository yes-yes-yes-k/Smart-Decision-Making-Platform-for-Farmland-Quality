## Commit List
8c180d3 feat: extend CoreEngine adapter with data import methods

## Diff Stat
 framework/core_engine/adapter.py | 37 +++++++++++++++++++++++++++++
 tests/test_precompute.py         | 51 ++++++++++++++++++++++++++++++++++++++++
 2 files changed, 88 insertions(+)

## Full Diff
diff --git a/framework/core_engine/adapter.py b/framework/core_engine/adapter.py
index 91a9130..222607f 100644
--- a/framework/core_engine/adapter.py
+++ b/framework/core_engine/adapter.py
@@ -105,11 +105,48 @@ class CoreEngine:
     def verify_runtime(self) -> Dict[str, Any]:
         self._ensure_import()
         try:
             return self._verify_standalone_runtime()
         except Exception as e:
             return {
                 "status": "error",
                 "error": {"code": "VERIFY_ERROR", "message": str(e)}
             }
 
+    def _ensure_data_import_imports(self):
+        """延迟导入数据导入相关模块，避免在 _ensure_import 中引入 geopandas 等重依赖。"""
+        if not hasattr(self, '_data_import_ready'):
+            from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate
+            from src.ai_culti_demo.farmland_stability.precompute import main as precompute_main
+            from src.ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
+            self._bulk_evaluate = bulk_evaluate
+            self._precompute_main = precompute_main
+            self._FarmlandGradeRunner = FarmlandGradeRunner
+            self._data_import_ready = True
+
+    def bulk_evaluate_csv(self, csv_path: str) -> Dict[str, Any]:
+        self._ensure_import()
+        self._ensure_data_import_imports()
+        try:
+            return self._bulk_evaluate(csv_path)
+        except Exception as e:
+            return {"status": "error", "error": {"code": "BULK_EVALUATE_ERROR", "message": str(e)}}
+
+    def precompute_stability(self, shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
+        self._ensure_import()
+        self._ensure_data_import_imports()
+        try:
+            return self._precompute_main(shapefile_dir, manifest)
+        except Exception as e:
+            return {"status": "error", "error": {"code": "PRECOMPUTE_ERROR", "message": str(e)}}
+
+    def check_grade_eval_deployment(self) -> Dict[str, Any]:
+        self._ensure_import()
+        self._ensure_data_import_imports()
+        try:
+            runner = self._FarmlandGradeRunner()
+            result = runner.check_deployment()
+            return {"deployment_ok": True, "detail": result} if result else {"deployment_ok": False, "detail": None}
+        except Exception as e:
+            return {"deployment_ok": False, "error": {"code": "DEPLOYMENT_CHECK_ERROR", "message": str(e)}}
+
 core_engine = CoreEngine()
diff --git a/tests/test_precompute.py b/tests/test_precompute.py
index eaa5759..9a3aa83 100644
--- a/tests/test_precompute.py
+++ b/tests/test_precompute.py
@@ -77,10 +77,61 @@ def test_main_full_flow_with_mocks():
 
         assert result['status'] == 'ok'
         assert result['processed'] == 1
         assert result['saved_to_db'] == 1
         assert len(result['output_files']) == 2
         m_run.assert_called_once()
         m_storage_cls.assert_called_once()
         mock_storage.create_tables.assert_called_once()
         mock_storage.save_results.assert_called_once()
         m_save_final.assert_called_once()
+
+
+def test_adapter_bulk_evaluate_csv_delegates():
+    """验证 adapter.bulk_evaluate_csv 委托给 bulk_evaluate 并捕获异常。"""
+    from framework.core_engine.adapter import CoreEngine
+
+    engine = CoreEngine()
+
+    with patch('src.ai_culti_demo.farmland_diagnosis.evaluation.bulk_evaluate', return_value={"status": "ok", "processed": 5}) as m:
+        result = engine.bulk_evaluate_csv("/fake/test.csv")
+        assert result["status"] == "ok"
+        assert result["processed"] == 5
+        m.assert_called_once_with("/fake/test.csv")
+
+
+def test_adapter_bulk_evaluate_csv_error_handling():
+    """验证 adapter.bulk_evaluate_csv 捕获异常返回错误字典。"""
+    from framework.core_engine.adapter import CoreEngine
+
+    engine = CoreEngine()
+
+    with patch('src.ai_culti_demo.farmland_diagnosis.evaluation.bulk_evaluate', side_effect=RuntimeError("boom")):
+        result = engine.bulk_evaluate_csv("/fake/test.csv")
+        assert result["status"] == "error"
+        assert result["error"]["code"] == "BULK_EVALUATE_ERROR"
+        assert "boom" in result["error"]["message"]
+
+
+def test_adapter_precompute_stability_delegates():
+    """验证 adapter.precompute_stability 委托给 precompute.main。"""
+    from framework.core_engine.adapter import CoreEngine
+
+    engine = CoreEngine()
+    manifest = {"current_filename": "2024.shp", "history_filenames": ["2018.shp"], "years": [2018, 2024]}
+
+    with patch('src.ai_culti_demo.farmland_stability.precompute.main', return_value={"status": "ok", "processed": 10}) as m:
+        result = engine.precompute_stability("/fake/dir", manifest)
+        assert result["status"] == "ok"
+        m.assert_called_once_with("/fake/dir", manifest)
+
+
+def test_adapter_check_grade_eval_deployment_ok():
+    """验证 adapter.check_grade_eval_deployment 返回 deployment_ok。"""
+    from framework.core_engine.adapter import CoreEngine
+
+    engine = CoreEngine()
+
+    with patch('src.ai_culti_demo.farmland_grade_eval.runner.FarmlandGradeRunner') as MockRunner:
+        MockRunner.return_value.check_deployment.return_value = {"exe_exists": True, "dat_exists": True, "ready": True}
+        result = engine.check_grade_eval_deployment()
+        assert result["deployment_ok"] is True

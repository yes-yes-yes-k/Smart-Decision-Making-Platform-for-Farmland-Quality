from __future__ import annotations
from typing import Any, Dict, Optional

class CoreEngine:
    def __init__(self):
        self._initialized = False

    def _ensure_import(self):
        if not self._initialized:
            try:
                from src.ai_culti_demo.catalog import load_catalog, get_asset, get_layer
                from src.ai_culti_demo.overview import get_county_overview
                from src.ai_culti_demo.diagnosis import diagnose_county
                from src.ai_culti_demo.thematic_models import list_thematic_models, run_thematic_model
                from src.ai_culti_demo.report import build_report_summary
                from src.ai_culti_demo.runtime import verify_standalone_runtime

                self._load_catalog = load_catalog
                self._get_asset = get_asset
                self._get_layer = get_layer
                self._get_county_overview = get_county_overview
                self._diagnose_county = diagnose_county
                self._list_thematic_models = list_thematic_models
                self._run_thematic_model = run_thematic_model
                self._build_report_summary = build_report_summary
                self._verify_standalone_runtime = verify_standalone_runtime
                self._initialized = True
            except ImportError as e:
                raise RuntimeError(f"Failed to initialize core engine: {e}")

    def get_county_overview(self, area_code: str = "lechang") -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._get_county_overview(area_code)
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "CORE_ENGINE_ERROR", "message": str(e)}
            }

    def diagnose_county(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._diagnose_county(payload)
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "DIAGNOSIS_ERROR", "message": str(e)}
            }

    def list_thematic_models(self, area_code: str = "lechang") -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._list_thematic_models(area_code)
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "MODEL_LIST_ERROR", "message": str(e)}
            }

    def run_thematic_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._run_thematic_model(payload)
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "MODEL_RUN_ERROR", "message": str(e)}
            }

    def build_report_summary(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._build_report_summary(diagnosis)
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "REPORT_ERROR", "message": str(e)}
            }

    def load_catalog(self, path: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._load_catalog(path)
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "CATALOG_ERROR", "message": str(e)}
            }

    def get_asset(self, catalog: Dict[str, Any], asset_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_import()
        try:
            return self._get_asset(catalog, asset_id)
        except Exception:
            return None

    def get_layer(self, catalog: Dict[str, Any], layer_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_import()
        try:
            return self._get_layer(catalog, layer_id)
        except Exception:
            return None

    def verify_runtime(self) -> Dict[str, Any]:
        self._ensure_import()
        try:
            return self._verify_standalone_runtime()
        except Exception as e:
            return {
                "status": "error",
                "error": {"code": "VERIFY_ERROR", "message": str(e)}
            }

    def _ensure_data_import_imports(self):
        """延迟导入数据导入相关模块，避免在 _ensure_import 中引入 geopandas 等重依赖。"""
        if not hasattr(self, '_data_import_ready'):
            from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate
            from src.ai_culti_demo.farmland_stability.precompute import main as precompute_main
            from src.ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
            self._bulk_evaluate = bulk_evaluate
            self._precompute_main = precompute_main
            self._FarmlandGradeRunner = FarmlandGradeRunner
            self._data_import_ready = True

    def bulk_evaluate_csv(self, csv_path: str) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            return self._bulk_evaluate(csv_path)
        except Exception as e:
            return {"status": "error", "error": {"code": "BULK_EVALUATE_ERROR", "message": str(e)}}

    def precompute_stability(self, shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            return self._precompute_main(shapefile_dir, manifest)
        except Exception as e:
            return {"status": "error", "error": {"code": "PRECOMPUTE_ERROR", "message": str(e)}}

    def check_grade_eval_deployment(self) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            runner = self._FarmlandGradeRunner()
            result = runner.check_deployment()
            return {"deployment_ok": True, "detail": result} if result else {"deployment_ok": False, "detail": None}
        except Exception as e:
            return {"deployment_ok": False, "error": {"code": "DEPLOYMENT_CHECK_ERROR", "message": str(e)}}

core_engine = CoreEngine()

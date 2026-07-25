"""数据导入触发器：数据部署完成后调用对应专题模型的预计算/评价/校验入口。

每个触发函数通过 CoreEngine adapter 调用底层模型，使用线程池 + future.result(timeout=)
实现超时控制，超时抛 TimeoutError。trigger 不解释返回字典内容（成功/错误字典均原样透传）。
"""
import concurrent.futures
from typing import Any, Dict, Optional

from framework.config import Config
from framework.core_engine.adapter import core_engine

# 暴露 concurrent_futures 便于测试 monkeypatch
concurrent_futures = concurrent.futures


def _run_with_timeout(
    func,
    *args,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """在线程池中执行 func，超时抛内置 TimeoutError。

    Args:
        func: 要调用的函数
        *args: 传给 func 的位置参数
        timeout: 超时秒数；None 时取 Config.DATA_IMPORT_TIMEOUT
    """
    actual_timeout = timeout if timeout is not None else Config.DATA_IMPORT_TIMEOUT
    with concurrent_futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=actual_timeout)
        except concurrent_futures.TimeoutError as e:
            # 取消 future（仅当未开始时生效；已运行中的线程无法真正中断）
            future.cancel()
            raise TimeoutError(f"触发器执行超时（{actual_timeout}s）") from e


def trigger_csv_evaluate(csv_path: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """触发 CSV 批量评价：调用 adapter.bulk_evaluate_csv。

    Args:
        csv_path: 部署后的 CSV 文件路径
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.bulk_evaluate_csv, csv_path, timeout=timeout)


def trigger_shapefile_precompute(
    target_dir: str,
    manifest: Dict[str, Any],
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """触发 shapefile 预计算：调用 adapter.precompute_stability。

    Args:
        target_dir: shapefile 解压部署目录
        manifest: 包含 current_year/history_years/years/current_filename/history_filenames 的字典
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.precompute_stability, target_dir, manifest, timeout=timeout)


def trigger_dat_check(target_dir: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """触发 .dat 部署校验：调用 adapter.check_grade_eval_deployment。

    注意：target_dir 参数保留用于与其他触发器签名一致（API 路由层统一调用），
    但不传给 adapter —— check_grade_eval_deployment() 无参数，
    FarmlandGradeRunner 内部从配置解析 .dat 路径。

    Args:
        target_dir: .dat 部署目录（仅用于日志/上下文一致性）
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.check_grade_eval_deployment, timeout=timeout)

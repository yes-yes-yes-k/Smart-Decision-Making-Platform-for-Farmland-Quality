import subprocess
import os
import time
from typing import Dict, Any, Optional
from pathlib import Path

DEFAULT_EXE_PATH = "bin/farmland_quality_eval/Farmland_quality_evaluation.exe"
DEFAULT_DAT_PATH = "bin/farmland_quality_eval/Farmlands_Quality_Level_Database.dat"


class FarmlandGradeRunner:
    """耕地质量等级评价exe调用包装器"""

    def __init__(self, exe_path: str = None, dat_path: str = None, timeout: int = 30):
        self.exe_path = exe_path or DEFAULT_EXE_PATH
        self.dat_path = dat_path or DEFAULT_DAT_PATH
        self.timeout = timeout

    def check_deployment(self) -> Dict[str, Any]:
        """检查exe和dat文件是否已部署"""
        exe_exists = os.path.exists(self.exe_path)
        dat_exists = os.path.exists(self.dat_path)

        return {
            "exe_exists": exe_exists,
            "dat_exists": dat_exists,
            "exe_path": self.exe_path,
            "dat_path": self.dat_path,
            "ready": exe_exists and dat_exists
        }

    def parse_output(self, output: str) -> Dict[str, Any]:
        """解析exe输出为结构化JSON

        exe 实际输出格式（2026-07-25 验证）：
          地块代码：A0001
          经度：  112.973801
          ...
          ------------------- 原始指标值 -------------------
          酸碱度(SJD):    4.600
          ...
          ------------------------------------------------
          耕地质量综合指数：  0.6728
          耕地质量等级：10等
          ------------ 障碍度因子（从大到小） ------------
          质地构型    :  0.1690  中度障碍
          ...
        """
        lines = output.strip().split('\n')
        result = {
            "raw_output": output,
            "parcel_info": {},
            "indicators": [],
            "composite_index": None,
            "quality_grade": None,
            "obstacle_degree": []
        }

        current_section = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Section markers — match actual exe output (not generic labels)
            if '地块代码' in stripped and '：' in stripped:
                current_section = 'parcel'
            elif '原始指标值' in stripped:
                current_section = 'indicators'
                continue
            elif '障碍度因子' in stripped:
                current_section = 'obstacle'
                continue
            elif stripped.startswith('---') or stripped.startswith('==='):
                # Separator line — end current section (but keep scanning for composite)
                if current_section in ('indicators', 'obstacle'):
                    current_section = None
                continue
            elif stripped.startswith('|') and '评价指标' in stripped:
                # Table header — stop parsing indicators
                current_section = None
                continue

            # Composite index / quality grade — match anywhere (no section needed)
            if '耕地质量综合指数' in stripped:
                # 耕地质量综合指数：  0.6728
                for sep in ('：', ':'):
                    if sep in stripped:
                        val = stripped.split(sep, 1)[1].strip()
                        try:
                            result["composite_index"] = float(val)
                        except ValueError:
                            pass
                        break
                continue
            if '耕地质量等级' in stripped and '潜在' not in stripped:
                # 耕地质量等级：10等  (exclude 潜在耕地质量等级)
                for sep in ('：', ':'):
                    if sep in stripped:
                        result["quality_grade"] = stripped.split(sep, 1)[1].strip()
                        break
                continue

            if current_section == 'parcel':
                # 地块代码：A0001 / 经度：  112.973801 / 县区名称：武江区
                for sep in ('：', ':'):
                    if sep in stripped:
                        key, value = stripped.split(sep, 1)
                        result["parcel_info"][key.strip()] = value.strip()
                        break

            elif current_section == 'indicators':
                # 酸碱度(SJD):    4.600 / 耕层质地(GCZD): 黏壤土
                for sep in (':', '：'):
                    if sep in stripped:
                        key, value = stripped.split(sep, 1)
                        indicator = {
                            "name": key.strip(),
                            "raw_value": value.strip()
                        }
                        result["indicators"].append(indicator)
                        break

            elif current_section == 'obstacle':
                # 质地构型    :  0.1690  中度障碍
                for sep in (':', '：'):
                    if sep in stripped:
                        name_part, rest = stripped.split(sep, 1)
                        rest_parts = rest.strip().split()
                        if len(rest_parts) >= 2:
                            obstacle = {
                                "indicator": name_part.strip(),
                                "degree": float(rest_parts[0]),
                                "level": rest_parts[1]
                            }
                            result["obstacle_degree"].append(obstacle)
                        break

        return result

    def run(self, parcel_code: str) -> Dict[str, Any]:
        """调用exe进行质量等级评价"""
        deployment = self.check_deployment()
        if not deployment["ready"]:
            return {
                "status": "error",
                "error": {
                    "code": "DEPLOYMENT_ERROR",
                    "message": f"exe或dat文件缺失: exe={deployment['exe_exists']}, dat={deployment['dat_exists']}"
                }
            }

        try:
            # 不使用 encoding 参数（文本模式），手动编解码以避免
            # "bytes input to text stream" 和 "str has no decode" 的冲突
            proc = subprocess.Popen(
                [self.exe_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(self.exe_path) or os.getcwd(),
            )

            start_time = time.time()
            stdout, stderr = proc.communicate(
                input=f"{parcel_code}\nquit\n".encode('gbk'),
                timeout=self.timeout
            )

            elapsed = time.time() - start_time

            if proc.returncode != 0:
                return {
                    "status": "error",
                    "error": {
                        "code": "EXECUTION_ERROR",
                        "message": f"exe执行失败，返回码: {proc.returncode}",
                        "stderr": stderr.decode('gbk', errors='replace').strip()
                    }
                }

            output = stdout.decode('gbk', errors='replace')

            if "未找到" in output or "不存在" in output:
                return {
                    "status": "error",
                    "error": {
                        "code": "PARCEL_NOT_FOUND",
                        "message": f"未找到地块代码: {parcel_code}"
                    }
                }

            parsed = self.parse_output(output)

            return {
                "status": "ok",
                "parcel_code": parcel_code,
                "execution_time": round(elapsed, 2),
                "parcel_info": parsed["parcel_info"],
                "indicators": parsed["indicators"],
                "composite_index": parsed["composite_index"],
                "quality_grade": parsed["quality_grade"],
                "obstacle_degree": parsed["obstacle_degree"],
                "raw_output": output
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {
                "status": "error",
                "error": {
                    "code": "TIMEOUT",
                    "message": f"exe执行超时（{self.timeout}秒）"
                }
            }
        except Exception as e:
            # 确保子进程被清理，避免僵尸进程泄漏
            try:
                proc.kill()
                proc.communicate()
            except Exception:
                pass
            return {
                "status": "error",
                "error": {
                    "code": "UNKNOWN_ERROR",
                    "message": str(e)
                }
            }


def run_grade_evaluation(parcel_code: str, exe_path: str = None, dat_path: str = None) -> Dict[str, Any]:
    """便捷函数：调用exe进行质量等级评价"""
    runner = FarmlandGradeRunner(exe_path, dat_path)
    return runner.run(parcel_code)

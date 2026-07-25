import subprocess
import os
import re
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
        """解析exe输出为结构化JSON"""
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

        # 指标行正则：指标名(代码): 值
        indicator_pattern = re.compile(r'^(.+?)\((.+?)\)\s*[:：]\s*(.+)$')
        # 障碍度行正则：指标名 : 障碍度值 障碍类型
        obstacle_pattern = re.compile(r'^(.+?)\s*[:：]\s*([\d.]+)\s+(.+)$')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # section 标记识别（匹配 exe 实际输出关键词）
            if '原始指标值' in line:
                current_section = 'indicators'
                continue
            elif '障碍度因子' in line:
                current_section = 'obstacle'
                continue
            elif line.startswith('---'):
                # 普通分隔线，重置 section
                current_section = None
                continue
            elif line.startswith('地块代码') and ('：' in line or ':' in line):
                current_section = 'parcel'
            elif '耕地质量综合指数' in line:
                current_section = 'composite'
            elif '耕地质量等级' in line:
                current_section = 'composite'

            if current_section == 'parcel':
                # parcel_info：用中文 '：' 或英文 ':' 分隔
                if '：' in line:
                    key, value = line.split('：', 1)
                    result["parcel_info"][key.strip()] = value.strip()
                elif ':' in line:
                    key, value = line.split(':', 1)
                    result["parcel_info"][key.strip()] = value.strip()

            elif current_section == 'indicators':
                # indicators：指标名(代码): 值
                m = indicator_pattern.match(line)
                if m:
                    indicator = {
                        "name": m.group(1).strip(),
                        "code": m.group(2).strip(),
                        "raw_value": m.group(3).strip()
                    }
                    result["indicators"].append(indicator)

            elif current_section == 'composite':
                # composite：综合指数和质量等级
                if '耕地质量综合指数' in line:
                    m = re.search(r'([\d.]+)', line)
                    if m:
                        try:
                            result["composite_index"] = float(m.group(1))
                        except ValueError:
                            pass
                elif '耕地质量等级' in line:
                    if '：' in line:
                        parts = line.split('：', 1)
                        if len(parts) > 1:
                            result["quality_grade"] = parts[1].strip()
                    elif ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            result["quality_grade"] = parts[1].strip()

            elif current_section == 'obstacle':
                # obstacle：指标名 : 障碍度值 障碍类型
                m = obstacle_pattern.match(line)
                if m:
                    try:
                        degree = float(m.group(2))
                    except ValueError:
                        continue
                    obstacle = {
                        "rank": len(result["obstacle_degree"]) + 1,
                        "indicator": m.group(1).strip(),
                        "degree": degree,
                        "level": m.group(3).strip()
                    }
                    result["obstacle_degree"].append(obstacle)

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

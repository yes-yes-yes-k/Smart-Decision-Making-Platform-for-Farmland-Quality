"""从 Fortran exe 输出生成与 .dat 数据一致的 CSV。

运行 exe 查询所有 CSV 中的地块代码，解析输出，生成修正后的 CSV。
exe 不输出 MJ/JHXLLZ/JHXQLZ，这三个字段从现有 CSV 补充。
"""
import csv
import subprocess
import sys
import os
import re
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
EXE_PATH = ROOT / "bin" / "farmland_quality_eval" / "Farmland_quality_evaluation.exe"
EXE_DIR = ROOT / "bin" / "farmland_quality_eval"
CSV_PATH = ROOT / "bin" / "farmland_quality_eval" / "Farmland_quality_Level_Database.csv"

# 名称到编码的反向映射
ZDGC_NAMES = [
    '砂土及壤质砂土', '砂质壤土', '壤土', '粉（砂）质壤土',
    '砂质黏壤土', '黏壤土', '粉（砂）质黏壤土', '砂质黏土',
    '壤质粘土', '粉（砂）质黏土', '黏土', '重黏土'
]
PSNL_NAMES = ['充分满足', '满足', '基本满足', '不满足']
GGNL_NAMES = ['充分满足', '满足', '基本满足', '不满足']
DXBW_NAMES = [
    '平原低阶', '平原中阶', '平原高阶', '宽谷盆地', '山间盆地',
    '丘陵下部', '丘陵中部', '丘陵上部', '山地坡下', '山地坡中', '山地坡上'
]
ZDGX_NAMES = ['上松下紧型', '海绵型', '夹层型', '紧实型', '上紧下松型', '薄层型', '松散型']
XQMC_NAMES = [
    '乐昌市', '乳源瑶族自治县', '仁化县', '南雄市', '始兴县',
    '新丰县', '曲江区', '武江区', '浈江区', '翁源县'
]
EJNYQ_NAMES = [
    '闽南粤中农林水产区', '粤西桂南农林区', '琼雷及南海诸岛农林区', '南岭丘陵山地林农区'
]


def find_code(name, names_list):
    """模糊匹配名称到编码（1-indexed）。"""
    name = name.strip()
    for i, n in enumerate(names_list):
        if name == n.strip() or n.strip().startswith(name) or name.startswith(n.strip()):
            return i + 1
    return 0


def parse_exe_output(output: str):
    """解析 exe 输出，返回 {parcel_code: {field: value}} 字典。"""
    results = {}
    current_parcel = None
    current_data = {}

    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 地块代码
        m = re.match(r'地块代码[：:]\s*(\S+)', line)
        if m:
            if current_parcel and current_data:
                results[current_parcel] = current_data
            current_parcel = m.group(1).strip()
            current_data = {}
            continue

        if current_parcel is None:
            continue

        # 经度
        m = re.match(r'经度[：:]\s*([\d.]+)', line)
        if m:
            current_data['JD'] = float(m.group(1))
            continue

        # 纬度
        m = re.match(r'纬度[：:]\s*([\d.]+)', line)
        if m:
            current_data['WD'] = float(m.group(1))
            continue

        # 县区名称
        m = re.match(r'县区名称[：:]\s*(\S+)', line)
        if m:
            current_data['XQMCcode'] = find_code(m.group(1).strip(), XQMC_NAMES)
            continue

        # 二级农业区名称
        m = re.match(r'二级农业区名称[：:]\s*(\S+)', line)
        if m:
            current_data['EJNYQcode'] = find_code(m.group(1).strip(), EJNYQ_NAMES)
            continue

        # 数值型指标
        m = re.match(r'酸碱度\(SJD\):\s*([\d.]+)', line)
        if m:
            current_data['SJD'] = float(m.group(1))
            continue

        m = re.match(r'有机质含量\(YJZ\):\s*([\d.]+)', line)
        if m:
            current_data['YJZ'] = float(m.group(1))
            continue

        m = re.match(r'有效磷含量\(YXL\):\s*([\d.]+)', line)
        if m:
            current_data['YXL'] = float(m.group(1))
            continue

        m = re.match(r'速效钾含量\(SXJ\):\s*([\d.]+)', line)
        if m:
            current_data['SXJ'] = float(m.group(1))
            continue

        m = re.match(r'土壤容重\(TRRZ\):\s*([\d.]+)', line)
        if m:
            current_data['TRRZ'] = float(m.group(1))
            continue

        m = re.match(r'有效土层厚度\(YXTCHD\):\s*([\d.]+)', line)
        if m:
            current_data['YXTCHD'] = float(m.group(1))
            continue

        m = re.match(r'耕层厚度\(GCHD\):\s*([\d.]+)', line)
        if m:
            current_data['GCHD'] = float(m.group(1))
            continue

        # 概念型指标
        m = re.match(r'耕层质地\(GCZD\):\s*(\S+)', line)
        if m:
            current_data['GCZDcode'] = find_code(m.group(1).strip(), ZDGC_NAMES)
            continue

        m = re.match(r'排水能力\(PSNL\):\s*(\S+)', line)
        if m:
            current_data['PSNLcode'] = find_code(m.group(1).strip(), PSNL_NAMES)
            continue

        m = re.match(r'灌溉能力\(GGNL\):\s*(\S+)', line)
        if m:
            current_data['GGNLcode'] = find_code(m.group(1).strip(), GGNL_NAMES)
            continue

        m = re.match(r'地形部位\(DXBW\):\s*(\S+)', line)
        if m:
            current_data['DXBWcode'] = find_code(m.group(1).strip(), DXBW_NAMES)
            continue

        m = re.match(r'质地构型\(ZDGX\):\s*(\S+)', line)
        if m:
            current_data['ZDGXcode'] = find_code(m.group(1).strip(), ZDGX_NAMES)
            continue

        # 检测下一个地块查询开始（分隔线后）
        if line.startswith('---') and current_parcel and len(current_data) >= 12:
            # 输出结束区域
            pass

    # 最后一个地块
    if current_parcel and current_data:
        results[current_parcel] = current_data

    return results


def main():
    # 读取现有 CSV 获取地块代码和补充字段
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    parcel_codes = [row['SiteID'].strip() for row in csv_rows]
    print(f"CSV 中有 {len(parcel_codes)} 个地块")

    # 构建 exe 输入（所有地块代码 + quit）
    exe_input = '\n'.join(parcel_codes) + '\nquit\n'

    # 运行 exe
    print(f"运行 exe 查询 {len(parcel_codes)} 个地块...")
    proc = subprocess.run(
        [str(EXE_PATH)],
        input=exe_input.encode('gbk'),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(EXE_DIR),
        timeout=300,
    )
    output = proc.stdout.decode('gbk', errors='replace')
    print(f"exe 输出 {len(output)} 字节")

    # 解析输出
    exe_data = parse_exe_output(output)
    print(f"解析到 {len(exe_data)} 个地块的数据")

    # 生成修正后的 CSV
    fieldnames = ['SiteID', 'JD', 'WD', 'MJ', 'SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ',
                  'YXTCHD', 'GCHD', 'JHXLLZ', 'JHXQLZ', 'EJNYQcode', 'XQMCcode',
                  'GCZDcode', 'PSNLcode', 'GGNLcode', 'DXBWcode', 'ZDGXcode']

    output_path = CSV_PATH.parent / "Farmland_quality_Level_Database_corrected.csv"
    matched = 0
    mismatches = []

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for csv_row in csv_rows:
            code = csv_row['SiteID'].strip()
            exe_row = exe_data.get(code)

            if exe_row is None:
                # exe 中未找到，保留 CSV 原值
                writer.writerow(csv_row)
                mismatches.append(f"  {code}: exe 中未找到，保留 CSV 原值")
                continue

            matched += 1

            # 检查差异
            diffs = []
            for field in ['ZDGXcode', 'GCZDcode', 'DXBWcode', 'PSNLcode', 'GGNLcode',
                          'EJNYQcode', 'XQMCcode']:
                csv_val = int(csv_row[field])
                exe_val = exe_row.get(field, csv_val)
                if csv_val != exe_val:
                    diffs.append(f"{field}: CSV={csv_val} exe={exe_val}")

            for field in ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'YXTCHD', 'GCHD', 'JD', 'WD']:
                csv_val = float(csv_row[field])
                exe_val = exe_row.get(field, csv_val)
                if abs(csv_val - exe_val) > 0.001:
                    diffs.append(f"{field}: CSV={csv_val} exe={exe_val}")

            if diffs:
                mismatches.append(f"  {code}: {', '.join(diffs)}")

            # 合并：exe 值优先，MJ/JHXLLZ/JHXQLZ 从 CSV 补充
            merged = {}
            merged['SiteID'] = code
            merged['JD'] = exe_row.get('JD', float(csv_row['JD']))
            merged['WD'] = exe_row.get('WD', float(csv_row['WD']))
            merged['MJ'] = csv_row['MJ']  # exe 不输出
            merged['SJD'] = exe_row.get('SJD', float(csv_row['SJD']))
            merged['YJZ'] = exe_row.get('YJZ', float(csv_row['YJZ']))
            merged['YXL'] = exe_row.get('YXL', float(csv_row['YXL']))
            merged['SXJ'] = exe_row.get('SXJ', float(csv_row['SXJ']))
            merged['TRRZ'] = exe_row.get('TRRZ', float(csv_row['TRRZ']))
            merged['YXTCHD'] = exe_row.get('YXTCHD', float(csv_row['YXTCHD']))
            merged['GCHD'] = exe_row.get('GCHD', float(csv_row['GCHD']))
            merged['JHXLLZ'] = csv_row['JHXLLZ']  # exe 不输出
            merged['JHXQLZ'] = csv_row['JHXQLZ']  # exe 不输出
            merged['EJNYQcode'] = exe_row.get('EJNYQcode', int(csv_row['EJNYQcode']))
            merged['XQMCcode'] = exe_row.get('XQMCcode', int(csv_row['XQMCcode']))
            merged['GCZDcode'] = exe_row.get('GCZDcode', int(csv_row['GCZDcode']))
            merged['PSNLcode'] = exe_row.get('PSNLcode', int(csv_row['PSNLcode']))
            merged['GGNLcode'] = exe_row.get('GGNLcode', int(csv_row['GGNLcode']))
            merged['DXBWcode'] = exe_row.get('DXBWcode', int(csv_row['DXBWcode']))
            merged['ZDGXcode'] = exe_row.get('ZDGXcode', int(csv_row['ZDGXcode']))
            writer.writerow(merged)

    print(f"\n匹配: {matched}/{len(parcel_codes)}")
    print(f"差异: {len(mismatches)} 个地块")
    if mismatches:
        print("差异详情（前 20 个）:")
        for m in mismatches[:20]:
            print(m)
        if len(mismatches) > 20:
            print(f"  ... 还有 {len(mismatches) - 20} 个")

    print(f"\n修正后的 CSV: {output_path}")


if __name__ == '__main__':
    main()

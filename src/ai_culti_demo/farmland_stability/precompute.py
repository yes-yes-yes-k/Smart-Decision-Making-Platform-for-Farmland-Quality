"""稳定性模型离线预计算入口。

封装 run_all_models → StabilityStorage.save_results → save_final_results 完整流程。
支持 `python -m ai_culti_demo.farmland_stability.precompute` 命令行调用（见 data/farmland_stability/README.md）。
"""
import os
from typing import Any, Dict, List

from .model import run_all_models, save_final_results, MODULE_FIELDS, RESULT_CN
from .storage import StabilityStorage


def g_to_records(G, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ') -> List[Dict[str, Any]]:
    """将 GeoDataFrame G 转换为 StabilityStorage.save_results 期望的 records 列表。

    每条 record 包含：
    - parcel_id / region / score / grade：基础字段
    - module_1..9：各模块字段值的字典（中文 key，来自 RESULT_CN 映射）
    - all_results：汇总所有模块的字典
    """
    records = []
    for _, row in G.iterrows():
        record = {
            'parcel_id': str(row[id_col]),
            'region': row.get(region),
            'score': row.get(score),
            'grade': row.get(grade),
        }
        all_results = {}
        for module_num, fields in MODULE_FIELDS.items():
            module_data = {}
            for f in fields:
                if f in row.index:
                    module_data[RESULT_CN.get(f, f)] = row[f]
            record[f'module_{module_num}'] = module_data
            all_results[f'module_{module_num}'] = module_data
        record['all_results'] = all_results
        records.append(record)
    return records


def main(shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """完整预计算流程：run_all_models → DB 持久化 → 文件输出。

    Args:
        shapefile_dir: shapefile 所在目录
        manifest: 含 current_filename / history_filenames / years 的字典；
            可选 id_column 指定地块统一编码字段，模型1 v2 使用 TYBH。

    Returns:
        {status, processed, saved_to_db, output_files}
    """
    current_file = os.path.join(shapefile_dir, manifest['current_filename'])
    history_files = [os.path.join(shapefile_dir, f) for f in manifest['history_filenames']]
    years = manifest['years']
    id_col = manifest.get('id_column', 'ID')

    G = run_all_models(current_file, history_files, years, id_col=id_col)

    # DB 持久化
    storage = StabilityStorage()
    storage.create_tables()
    records = g_to_records(G, id_col=id_col)
    saved_count = storage.save_results(records)

    # 文件持久化（shapefile + xlsx，供在线查询重载）
    shp_file = os.path.join(shapefile_dir, 'stability_results.shp')
    xlsx_file = os.path.join(shapefile_dir, 'stability_results.xlsx')
    save_final_results(G, shp_file, xlsx_file, years)

    return {
        'status': 'ok',
        'processed': len(records),
        'saved_to_db': saved_count,
        'output_files': [shp_file, xlsx_file]
    }


if __name__ == '__main__':
    # 命令行入口：从 data/farmland_stability/ 读取默认 manifest 并运行
    import json
    default_dir = 'data/farmland_stability'
    manifest_path = os.path.join(default_dir, 'manifest.json')
    if not os.path.exists(manifest_path):
        print(f"错误：未找到 {manifest_path}")
        raise SystemExit(1)
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    result = main(default_dir, manifest)
    print(result)

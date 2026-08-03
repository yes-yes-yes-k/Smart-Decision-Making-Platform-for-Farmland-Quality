import csv
from typing import List
from .models import Parcel

def load_parcels_from_csv(filename: str) -> List[Parcel]:
    """从 UTF-8-sig CSV 文件加载地块数据。

    Args:
        filename: CSV 文件路径，首行为表头，后续每行 20 字段。

    Returns:
        Parcel 列表。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 行解析失败（字段值类型转换错误）。
    """
    parcels = []
    with open(filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)  # 标题行
        for lineno, row in enumerate(reader, start=2):
            if not row or len(row) < 20:
                print(f'警告：第 {lineno} 行字段不足，已跳过。')
                continue
            try:
                parcel = Parcel(
                    tybh=row[0],
                    jd=float(row[1]), wd=float(row[2]), mj=float(row[3]),
                    sjd=float(row[4]), yjz=float(row[5]), yxl=float(row[6]),
                    sxj=float(row[7]), trrz=float(row[8]), yxtchd=float(row[9]),
                    gchd=float(row[10]), jhxllz=float(row[11]), jhxqlz=float(row[12]),
                    ejnyq=int(row[13]), xqmc=int(row[14]),
                    zdgc=int(row[15]), psnl=int(row[16]), ggnl=int(row[17]),
                    dxbw=int(row[18]), zdgx=int(row[19])
                )
                parcels.append(parcel)
            except (ValueError, IndexError) as e:
                raise ValueError(f'第 {lineno} 行解析失败: {e}') from e
    return parcels

"""清理 parcel_info 和 parcel_history_snapshot 中的离散值空白字符。"""
import json
import os
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

env_path = _PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

import psycopg2

DISCRETE_FIELDS = [
    "soil_texture", "irrigation_condition", "drainage_capacity",
    "terrain_position", "soil_structure",
]

# 标准值映射（清理后 → 标准值）
VALUE_NORMALIZE = {
    "充分满足": "充分满足",
    "满足": "满足",
    "基本满足": "基本满足",
    "不满足": "不满足",
}


def clean_str(s):
    """移除所有非汉字非字母非数字非括号字符。"""
    if s is None:
        return None
    # 保留汉字、字母、数字、括号
    cleaned = re.sub(r"[^\u4e00-\u9fff()a-zA-Z0-9]", "", str(s))
    return cleaned if cleaned else None


def normalize_value(field, val):
    """标准化离散值。"""
    if val is None:
        return None
    cleaned = clean_str(val)
    if cleaned is None:
        return None
    # 尝试匹配标准值
    for standard, _ in VALUE_NORMALIZE.items():
        if cleaned == standard:
            return standard
    # 未匹配的直接返回清理后的值
    return cleaned


conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", ""),
    dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
)
cur = conn.cursor()

# 清理 parcel_info
cur.execute("SELECT parcel_id, soil_indicators FROM parcel_info WHERE parcel_id NOT LIKE 'P-VERIFY-%'")
rows = cur.fetchall()
print(f"清理 parcel_info: {len(rows)} 条")
updated = 0
for parcel_id, si in rows:
    if not si:
        continue
    si_dict = si if isinstance(si, dict) else json.loads(si)
    changed = False
    for field in DISCRETE_FIELDS:
        if field in si_dict and si_dict[field]:
            cleaned = normalize_value(field, si_dict[field])
            if cleaned != si_dict[field]:
                si_dict[field] = cleaned
                changed = True
    if changed:
        cur.execute(
            "UPDATE parcel_info SET soil_indicators = %s::json WHERE parcel_id = %s",
            (json.dumps(si_dict, ensure_ascii=False), parcel_id),
        )
        updated += 1
conn.commit()
print(f"  更新了 {updated} 条")

# 清理 parcel_history_snapshot
cur.execute("SELECT id, soil_indicators FROM parcel_history_snapshot")
rows = cur.fetchall()
print(f"清理 parcel_history_snapshot: {len(rows)} 条")
updated = 0
for row_id, si in rows:
    if not si:
        continue
    si_dict = si if isinstance(si, dict) else json.loads(si)
    changed = False
    for field in DISCRETE_FIELDS:
        if field in si_dict and si_dict[field]:
            cleaned = normalize_value(field, si_dict[field])
            if cleaned != si_dict[field]:
                si_dict[field] = cleaned
                changed = True
    if changed:
        cur.execute(
            "UPDATE parcel_history_snapshot SET soil_indicators = %s::json WHERE id = %s",
            (json.dumps(si_dict, ensure_ascii=False), row_id),
        )
        updated += 1
conn.commit()
print(f"  更新了 {updated} 条")

# 验证
cur.execute("""
    SELECT soil_indicators->>'irrigation_condition', COUNT(*)
    FROM parcel_info WHERE parcel_id NOT LIKE 'P-VERIFY-%'
    GROUP BY soil_indicators->>'irrigation_condition'
    ORDER BY COUNT(*) DESC
""")
print("\nirrigation_condition 值分布:")
for val, count in cur.fetchall():
    print(f"  '{val}': {count}")

conn.close()
print("\nDone.")

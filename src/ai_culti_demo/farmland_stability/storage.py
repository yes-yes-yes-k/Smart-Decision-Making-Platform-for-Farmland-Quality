import sqlite3
import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

DEFAULT_DB_PATH = "data/farmland_stability/stability_results.db"


class StabilityStorage:
    """模型1稳定性风险结果的SQLite存储模块"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = None

    def _connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def create_tables(self) -> None:
        """创建稳定性风险结果表"""
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stability_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcel_id TEXT NOT NULL,
                region TEXT,
                score REAL,
                grade TEXT,
                module_1 TEXT,
                module_2 TEXT,
                module_3 TEXT,
                module_4 TEXT,
                module_5 TEXT,
                module_6 TEXT,
                module_7 TEXT,
                module_8 TEXT,
                module_9 TEXT,
                all_results TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(parcel_id)
            )
        ''')

        conn.commit()

    def save_results(self, records: List[Dict[str, Any]]) -> int:
        """保存稳定性风险结果"""
        conn = self._connect()
        cursor = conn.cursor()

        count = 0
        for record in records:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO stability_results 
                    (parcel_id, region, score, grade, module_1, module_2, module_3, 
                     module_4, module_5, module_6, module_7, module_8, module_9, all_results)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('parcel_id'),
                    record.get('region'),
                    record.get('score'),
                    record.get('grade'),
                    json.dumps(record.get('module_1', {})),
                    json.dumps(record.get('module_2', {})),
                    json.dumps(record.get('module_3', {})),
                    json.dumps(record.get('module_4', {})),
                    json.dumps(record.get('module_5', {})),
                    json.dumps(record.get('module_6', {})),
                    json.dumps(record.get('module_7', {})),
                    json.dumps(record.get('module_8', {})),
                    json.dumps(record.get('module_9', {})),
                    json.dumps(record.get('all_results', {}))
                ))
                count += 1
            except Exception as e:
                print(f"Error saving parcel {record.get('parcel_id')}: {e}")

        conn.commit()
        return count

    def get_result(self, parcel_id: str, module: int = None) -> Optional[Dict[str, Any]]:
        """查询地块稳定性风险结果"""
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM stability_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        result = {
            'parcel_id': row['parcel_id'],
            'region': row['region'],
            'score': row['score'],
            'grade': row['grade'],
            'module_1': json.loads(row['module_1']) if row['module_1'] else {},
            'module_2': json.loads(row['module_2']) if row['module_2'] else {},
            'module_3': json.loads(row['module_3']) if row['module_3'] else {},
            'module_4': json.loads(row['module_4']) if row['module_4'] else {},
            'module_5': json.loads(row['module_5']) if row['module_5'] else {},
            'module_6': json.loads(row['module_6']) if row['module_6'] else {},
            'module_7': json.loads(row['module_7']) if row['module_7'] else {},
            'module_8': json.loads(row['module_8']) if row['module_8'] else {},
            'module_9': json.loads(row['module_9']) if row['module_9'] else {},
            'all_results': json.loads(row['all_results']) if row['all_results'] else {}
        }

        if module is not None and 1 <= module <= 9:
            return {f'module_{module}': result[f'module_{module}']}

        return result

    def is_ready(self) -> bool:
        """检查数据库是否就绪"""
        if not os.path.exists(self.db_path):
            return False

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stability_results'")
            return cursor.fetchone() is not None
        except:
            return False

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

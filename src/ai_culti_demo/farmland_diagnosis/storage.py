import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


# 标准指标码（与 config.ALL_INDICATORS 一致，此处本地声明避免循环导入）
_ALL_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX', 'YXTCHD', 'GCHD', 'JHX', 'JLA']
_DISCRETE_INDICATORS = {'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX'}


class DiagnosisStorage:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_dir = os.path.join(os.path.dirname(__file__), '../../data/farmland_diagnosis')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'farmland_diagnosis.db')
        self.db_path = db_path
        self._ensure_connection()

    def _ensure_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA foreign_keys = ON')
        conn.close()

    def create_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # evaluation_results：原始值列 + 隶属度列(xxxLSD) + 障碍等级列(xxxZADJ) + 障碍度列(xxxZAD) + ZHQZ + GDZLDJ
        eval_cols = [
            'parcel_id TEXT PRIMARY KEY',
            'region_code TEXT',
            'secondary_region_code TEXT',
        ]
        for ind in _ALL_INDICATORS:
            col_type = 'TEXT' if ind in _DISCRETE_INDICATORS else 'REAL'
            eval_cols.append(f'{ind} {col_type}')
        for ind in _ALL_INDICATORS:
            eval_cols.append(f'{ind}LSD REAL')
            eval_cols.append(f'{ind}ZADJ TEXT')
            eval_cols.append(f'{ind}ZAD REAL')
        eval_cols.append('ZHQZ REAL')
        eval_cols.append('GDZLDJ TEXT')
        eval_cols.append('created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        eval_cols.append('updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        cursor.execute(f'CREATE TABLE IF NOT EXISTS evaluation_results ({", ".join(eval_cols)})')

        # diagnosis_results：ZALX/ZYZAYS/CYZAYS + 各 xxxZADJ / xxxZAD
        diag_cols = [
            'parcel_id TEXT PRIMARY KEY REFERENCES evaluation_results(parcel_id)',
            'ZALX TEXT',
            'ZYZAYS TEXT',
            'CYZAYS TEXT',
        ]
        for ind in _ALL_INDICATORS:
            diag_cols.append(f'{ind}ZADJ TEXT')
            diag_cols.append(f'{ind}ZAD REAL')
        diag_cols.append('created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        cursor.execute(f'CREATE TABLE IF NOT EXISTS diagnosis_results ({", ".join(diag_cols)})')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS acidification_results (
                parcel_id TEXT PRIMARY KEY REFERENCES evaluation_results(parcel_id),
                acidification_level TEXT,
                acidification_direction TEXT,
                target_pH REAL,
                lime_demand REAL,
                amendment_type TEXT,
                amendment_rate REAL,
                measures TEXT,
                expected_effect TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def save_evaluation(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        original_cols = _ALL_INDICATORS
        lsd_cols = [f'{ind}LSD' for ind in _ALL_INDICATORS]
        zadj_cols = [f'{ind}ZADJ' for ind in _ALL_INDICATORS]
        zad_cols = [f'{ind}ZAD' for ind in _ALL_INDICATORS]
        all_data_cols = (['parcel_id', 'region_code', 'secondary_region_code']
                         + original_cols + lsd_cols + zadj_cols + zad_cols
                         + ['ZHQZ', 'GDZLDJ', 'updated_at'])
        placeholders = ', '.join(['?'] * len(all_data_cols))
        col_sql = ', '.join(all_data_cols)

        for record in records:
            values = (
                [record.get('parcel_id'), record.get('region_code'), record.get('secondary_region_code')]
                + [record.get(ind) for ind in original_cols]
                + [record.get(c) for c in lsd_cols]
                + [record.get(c) for c in zadj_cols]
                + [record.get(c) for c in zad_cols]
                + [record.get('ZHQZ'), record.get('GDZLDJ'), datetime.now()]
            )
            cursor.execute(
                f'INSERT OR REPLACE INTO evaluation_results ({col_sql}) VALUES ({placeholders})',
                values,
            )

        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count

    def save_diagnosis(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        zadj_cols = [f'{ind}ZADJ' for ind in _ALL_INDICATORS]
        zad_cols = [f'{ind}ZAD' for ind in _ALL_INDICATORS]
        all_data_cols = (['parcel_id', 'ZALX', 'ZYZAYS', 'CYZAYS']
                         + zadj_cols + zad_cols)
        placeholders = ', '.join(['?'] * len(all_data_cols))
        col_sql = ', '.join(all_data_cols)

        for record in records:
            values = (
                [record.get('parcel_id'), record.get('ZALX'), record.get('ZYZAYS'), record.get('CYZAYS')]
                + [record.get(c) for c in zadj_cols]
                + [record.get(c) for c in zad_cols]
            )
            cursor.execute(
                f'INSERT OR REPLACE INTO diagnosis_results ({col_sql}) VALUES ({placeholders})',
                values,
            )

        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count

    def save_acidification(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for record in records:
            cursor.execute('''
                INSERT OR REPLACE INTO acidification_results
                (parcel_id, acidification_level, acidification_direction,
                 target_pH, lime_demand, amendment_type, amendment_rate, measures, expected_effect)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record['parcel_id'], record.get('acidification_level'), record.get('acidification_direction'),
                record.get('target_pH'), record.get('lime_demand'), record.get('amendment_type'),
                record.get('amendment_rate'), json.dumps(record.get('measures', [])), record.get('expected_effect'),
            ))

        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count

    def get_evaluation(self, parcel_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM evaluation_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def get_diagnosis(self, parcel_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM diagnosis_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        columns = [desc[0] for desc in cursor.description]
        # ZALX/ZYZAYS/CYZAYS 及 xxxZADJ/xxxZAD 均为标量列，不再 JSON loads
        return dict(zip(columns, row))

    def get_acidification(self, parcel_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM acidification_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        result['measures'] = json.loads(result.get('measures', '[]'))
        return result

    def is_ready(self) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evaluation_results'")
        eval_exists = cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='diagnosis_results'")
        diag_exists = cursor.fetchone() is not None

        if eval_exists:
            cursor.execute('SELECT COUNT(*) FROM evaluation_results')
            eval_count = cursor.fetchone()[0]
        else:
            eval_count = 0

        if diag_exists:
            cursor.execute('SELECT COUNT(*) FROM diagnosis_results')
            diag_count = cursor.fetchone()[0]
        else:
            diag_count = 0

        conn.close()
        return eval_exists and diag_exists and eval_count > 0 and diag_count > 0

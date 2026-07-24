import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluation_results (
                parcel_id TEXT PRIMARY KEY,
                region_code TEXT,
                secondary_region_code TEXT,
                PH REAL, YJ REAL, YXP REAL, SXK REAL, RZ REAL,
                GZ TEXT, GG TEXT, PS TEXT, DX TEXT, ZD TEXT,
                YXT REAL, GCH REAL,
                PH_LD REAL, YJ_LD REAL, YXP_LD REAL, SXK_LD REAL, RZ_LD REAL,
                GZ_LD REAL, GG_LD REAL, PS_LD REAL, DX_LD REAL, ZD_LD REAL,
                YXT_LD REAL, GCH_LD REAL,
                composite_weight REAL,
                grade TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS diagnosis_results (
                parcel_id TEXT PRIMARY KEY REFERENCES evaluation_results(parcel_id),
                obstacle_type TEXT,
                main_factors TEXT,
                secondary_factors TEXT,
                PH_obstacle_level TEXT, YJ_obstacle_level TEXT,
                YXP_obstacle_level TEXT, SXK_obstacle_level TEXT,
                RZ_obstacle_level TEXT, GZ_obstacle_level TEXT,
                GG_obstacle_level TEXT, PS_obstacle_level TEXT,
                DX_obstacle_level TEXT, ZD_obstacle_level TEXT,
                YXT_obstacle_level TEXT, GCH_obstacle_level TEXT,
                PH_obstacle_degree REAL, YJ_obstacle_degree REAL,
                YXP_obstacle_degree REAL, SXK_obstacle_degree REAL,
                RZ_obstacle_degree REAL, GZ_obstacle_degree REAL,
                GG_obstacle_degree REAL, PS_obstacle_degree REAL,
                DX_obstacle_degree REAL, ZD_obstacle_degree REAL,
                YXT_obstacle_degree REAL, GCH_obstacle_degree REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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

        for record in records:
            cursor.execute('''
                INSERT OR REPLACE INTO evaluation_results
                (parcel_id, region_code, secondary_region_code,
                 PH, YJ, YXP, SXK, RZ, GZ, GG, PS, DX, ZD, YXT, GCH,
                 PH_LD, YJ_LD, YXP_LD, SXK_LD, RZ_LD,
                 GZ_LD, GG_LD, PS_LD, DX_LD, ZD_LD, YXT_LD, GCH_LD,
                 composite_weight, grade, updated_at)
                VALUES (?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?)
            ''', (
                record['parcel_id'], record.get('region_code'), record.get('secondary_region_code'),
                record.get('PH'), record.get('YJ'), record.get('YXP'), record.get('SXK'), record.get('RZ'),
                record.get('GZ'), record.get('GG'), record.get('PS'), record.get('DX'), record.get('ZD'),
                record.get('YXT'), record.get('GCH'),
                record.get('PH_LD'), record.get('YJ_LD'), record.get('YXP_LD'), record.get('SXK_LD'), record.get('RZ_LD'),
                record.get('GZ_LD'), record.get('GG_LD'), record.get('PS_LD'), record.get('DX_LD'), record.get('ZD_LD'),
                record.get('YXT_LD'), record.get('GCH_LD'),
                record.get('composite_weight'), record.get('grade'), datetime.now()
            ))

        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count

    def save_diagnosis(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for record in records:
            cursor.execute('''
                INSERT OR REPLACE INTO diagnosis_results
                (parcel_id, obstacle_type, main_factors, secondary_factors,
                 PH_obstacle_level, YJ_obstacle_level, YXP_obstacle_level, SXK_obstacle_level,
                 RZ_obstacle_level, GZ_obstacle_level, GG_obstacle_level, PS_obstacle_level,
                 DX_obstacle_level, ZD_obstacle_level, YXT_obstacle_level, GCH_obstacle_level,
                 PH_obstacle_degree, YJ_obstacle_degree, YXP_obstacle_degree, SXK_obstacle_degree,
                 RZ_obstacle_degree, GZ_obstacle_degree, GG_obstacle_degree, PS_obstacle_degree,
                 DX_obstacle_degree, ZD_obstacle_degree, YXT_obstacle_degree, GCH_obstacle_degree)
                VALUES (?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?)
            ''', (
                record['parcel_id'], record.get('obstacle_type'),
                json.dumps(record.get('main_factors', [])),
                json.dumps(record.get('secondary_factors', [])),
                record.get('PH_obstacle_level'), record.get('YJ_obstacle_level'),
                record.get('YXP_obstacle_level'), record.get('SXK_obstacle_level'),
                record.get('RZ_obstacle_level'), record.get('GZ_obstacle_level'),
                record.get('GG_obstacle_level'), record.get('PS_obstacle_level'),
                record.get('DX_obstacle_level'), record.get('ZD_obstacle_level'),
                record.get('YXT_obstacle_level'), record.get('GCH_obstacle_level'),
                record.get('PH_obstacle_degree'), record.get('YJ_obstacle_degree'),
                record.get('YXP_obstacle_degree'), record.get('SXK_obstacle_degree'),
                record.get('RZ_obstacle_degree'), record.get('GZ_obstacle_degree'),
                record.get('GG_obstacle_degree'), record.get('PS_obstacle_degree'),
                record.get('DX_obstacle_degree'), record.get('ZD_obstacle_degree'),
                record.get('YXT_obstacle_degree'), record.get('GCH_obstacle_degree')
            ))

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
                record.get('amendment_rate'), json.dumps(record.get('measures', [])), record.get('expected_effect')
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
        result = dict(zip(columns, row))
        result['main_factors'] = json.loads(result.get('main_factors', '[]'))
        result['secondary_factors'] = json.loads(result.get('secondary_factors', '[]'))
        return result

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

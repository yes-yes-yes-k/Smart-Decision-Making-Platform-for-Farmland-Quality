"""ParcelDataAccessor 单元测试。

不依赖真实 DB，使用 unittest.mock.patch 替换
framework.models.thematic_model.ParcelInfo 来验证查询与异常分支。

测试环境可能未安装 geoalchemy2，这里在导入 thematic_model 之前先 stub
一个 Geometry 类（返回 MagicMock 实例），避免 SQLAlchemy Column 在类定义
阶段调用 Geometry(...) 时因缺少 `_set_parent_with_dispatch` 而失败。
"""
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

if "geoalchemy2" not in sys.modules:
    _geo_stub = types.ModuleType("geoalchemy2")

    class _Geometry:
        """stub：返回 MagicMock，满足 SQLAlchemy Column 初始化所需协议。"""

        def __new__(cls, *args, **kwargs):
            return MagicMock()

    _geo_stub.Geometry = _Geometry
    sys.modules["geoalchemy2"] = _geo_stub

import framework.models.thematic_model  # noqa: F401  确保模块加载以便 patch 解析属性
from framework.domain.data.parcel_data_accessor import ParcelDataAccessor


class ParcelDataAccessorTests(unittest.TestCase):
    def test_returns_dict_when_parcel_exists(self):
        """DB 命中时返回 soil_indicators dict。"""
        fake_parcel = MagicMock()
        fake_parcel.soil_indicators = {"soil_ph": 5.5, "organic_matter": 2.1}
        mock_parcel_cls = MagicMock()
        mock_parcel_cls.query.filter_by.return_value.first.return_value = fake_parcel

        with patch(
            "framework.models.thematic_model.ParcelInfo",
            new=mock_parcel_cls,
        ):
            accessor = ParcelDataAccessor()
            result = accessor.get_parcel_indicators("P001")

        self.assertEqual(result, {"soil_ph": 5.5, "organic_matter": 2.1})
        mock_parcel_cls.query.filter_by.assert_called_once_with(parcel_id="P001")

    def test_returns_none_when_parcel_not_found(self):
        """DB 未命中时返回 None。"""
        mock_parcel_cls = MagicMock()
        mock_parcel_cls.query.filter_by.return_value.first.return_value = None

        with patch(
            "framework.models.thematic_model.ParcelInfo",
            new=mock_parcel_cls,
        ):
            accessor = ParcelDataAccessor()
            result = accessor.get_parcel_indicators("NOT_EXIST")

        self.assertIsNone(result)

    def test_returns_none_and_logs_on_db_exception(self):
        """DB 异常时返回 None 并记录 WARNING 日志。"""
        with patch("framework.models.thematic_model.ParcelInfo") as mock_model:
            mock_model.query.filter_by.side_effect = Exception("DB connection lost")
            with self.assertLogs(
                "framework.domain.data.parcel_data_accessor", level="WARNING"
            ) as cm:
                accessor = ParcelDataAccessor()
                result = accessor.get_parcel_indicators("P001")
            self.assertIsNone(result)
            self.assertTrue(any("查询 parcel_info 失败" in m for m in cm.output))


if __name__ == "__main__":
    unittest.main()

"""广东高清瓦片静态服务 Blueprint。

提供 XYZ 瓦片端点 `/gd_tiles/<z>/<x>/<y>.png`，供前端 Leaflet 叠加广东 100m 高清底图层。
瓦片由 `scripts/generate_basemap_tiles.py --source data/gd_tif_normalized.tif` 切片生成，
存放于 `agent_culti_demo/data/gd_basemap_tiles/{z}/{x}/{y}.png`。

设计要点：
- 公开端点（无 JWT），瓦片为静态底图资源
- 瓦片不存在时返回 404（不抛 500），不影响其他瓦片请求
- 仅开发环境使用；生产环境由 Nginx 直接 alias 托管，绕过 Flask
- 与 tiles_bp（全国 500m）独立，互不干扰
"""
from pathlib import Path

from flask import Blueprint, send_from_directory

gd_tiles_bp = Blueprint("gd_tiles", __name__)

# 广东瓦片根目录：项目根 / data / gd_basemap_tiles
_GD_TILES_DIR = Path(__file__).resolve().parents[3] / "data" / "gd_basemap_tiles"


@gd_tiles_bp.route("/gd_tiles/<int:z>/<int:x>/<int:y>.png", methods=["GET"])
def get_gd_tile(z: int, x: int, y: int):
    """按 XYZ 坐标返回广东高清瓦片 PNG；不存在则 404。"""
    return send_from_directory(_GD_TILES_DIR / str(z) / str(x), f"{y}.png")

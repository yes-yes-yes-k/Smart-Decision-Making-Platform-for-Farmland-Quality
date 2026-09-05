"""本地瓦片静态服务 Blueprint。

提供 XYZ 瓦片端点 `/tiles/<z>/<x>/<y>.png`，供前端 Leaflet 底图加载。
瓦片由 `scripts/generate_basemap_tiles.py` 离线切片生成，存放于
`agent_culti_demo/data/basemap_tiles/{z}/{x}/{y}.png`。

设计要点：
- 公开端点（无 JWT），瓦片为静态底图资源
- 瓦片不存在时返回 404（不抛 500），不影响其他瓦片请求
- 仅开发环境使用；生产环境由 Nginx 直接 alias 托管，绕过 Flask
"""
from pathlib import Path

from flask import Blueprint, send_from_directory

tiles_bp = Blueprint("tiles", __name__)

# 瓦片根目录：项目根 / data / basemap_tiles
_TILES_DIR = Path(__file__).resolve().parents[3] / "data" / "basemap_tiles"


@tiles_bp.route("/tiles/<int:z>/<int:x>/<int:y>.png", methods=["GET"])
def get_tile(z: int, x: int, y: int):
    """按 XYZ 坐标返回瓦片 PNG；不存在则 404。"""
    return send_from_directory(_TILES_DIR / str(z) / str(x), f"{y}.png")

"""将源 GeoTIFF 切片为 XYZ 瓦片金字塔（Leaflet 兼容）。

用途：
  将 E:\\Agent\\一张图地图\\China_RGB_500m_vis\\China_RGB_500m_vis.tif 切片为
  Web Mercator（EPSG:3857）XYZ 瓦片，输出至 agent_culti_demo/data/basemap_tiles/，
  供前端 Leaflet 底图加载（/tiles/{z}/{x}/{y}.png）。

环境依赖：
  - GDAL >= 3.5（提供 gdal2tiles 命令与 --xyz 选项）
  - 推荐通过 conda 安装：conda install -c conda-forge gdal

使用：
  python scripts/generate_basemap_tiles.py                     # 默认参数
  python scripts/generate_basemap_tiles.py --zoom 4-8         # 指定 zoom 范围
  python scripts/generate_basemap_tiles.py --force            # 清理已有输出目录后重建
  python scripts/generate_basemap_tiles.py --reproject        # 强制重投影（源非 3857 时使用）
  python scripts/generate_basemap_tiles.py --processes 4     # 指定并行进程数
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 项目根目录：scripts/ 的上一级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认参数（基于源 TIF 实测：EPSG:3857, 500m/px, 覆盖 72-138°E, 6-72°N）
DEFAULT_SOURCE_TIF = r"E:\Agent\一张图地图\China_RGB_500m_vis\China_RGB_500m_vis.tif"
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "data" / "basemap_tiles"
DEFAULT_ZOOM = "4-8"
DEFAULT_PROCESSES = max(1, (os.cpu_count() or 4) - 1)

# Miniforge3 安装位置（切片脚本依赖 GDAL CLI）
_MINIFORGE_ROOT = Path(r"C:\Users\Karry\miniforge3")


def _setup_gdal_env() -> None:
    """将 Miniforge3 的 GDAL bin 与 GDAL_DATA 加入环境，确保 gdal2tiles 可用。"""
    bin_dir = _MINIFORGE_ROOT / "Library" / "bin"
    gdal_data = _MINIFORGE_ROOT / "Library" / "share" / "gdal"
    os.environ["Path"] = (
        str(_MINIFORGE_ROOT)
        + os.pathsep
        + str(_MINIFORGE_ROOT / "Scripts")
        + os.pathsep
        + str(bin_dir)
        + os.pathsep
        + os.environ.get("Path", "")
    )
    if gdal_data.exists():
        os.environ.setdefault("GDAL_DATA", str(gdal_data))


def _check_gdal() -> None:
    """校验 GDAL 环境可用性；不可用时打印安装指引并以非零状态码退出。"""
    try:
        result = subprocess.run(
            ["gdal2tiles", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise FileNotFoundError("gdal2tiles 返回非零")
        version_line = (result.stdout or result.stderr or "").strip().splitlines()[0] if (result.stdout or result.stderr) else ""
        print(f"[OK] GDAL 可用：{version_line}")
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(
            "[FAIL] 未找到 gdal2tiles 命令。请安装 GDAL：\n"
            "  推荐（Windows）：安装 Miniforge3 后执行\n"
            "    conda install -c conda-forge gdal\n"
            "  或安装 OSGeo4W64 并勾选 gdal 包。\n"
            f"  错误详情：{e}",
            file=sys.stderr,
        )
        sys.exit(2)


def _check_source(tif_path: Path) -> None:
    """校验源 TIF 存在性，缺失时报错退出。"""
    if not tif_path.exists():
        print(f"[FAIL] 源 TIF 不存在：{tif_path}", file=sys.stderr)
        sys.exit(3)
    size_mb = tif_path.stat().st_size / (1024 * 1024)
    print(f"[OK] 源 TIF：{tif_path}（{size_mb:.1f} MB）")


def _prepare_output(out_dir: Path, force: bool) -> None:
    """处理输出目录已存在情况：force=True 清理重建；否则提示并退出。"""
    if out_dir.exists() and any(out_dir.iterdir()):
        if not force:
            print(
                f"[FAIL] 输出目录已非空：{out_dir}\n"
                "  使用 --force 清理后重建，或手动删除该目录。",
                file=sys.stderr,
            )
            sys.exit(4)
        print(f"[WARN] --force 模式：清理 {out_dir} ...")
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[OK] 输出目录：{out_dir}")


def _reproject_if_needed(
    tif_path: Path, force_reproject: bool, work_dir: Path
) -> Path:
    """若 --reproject 指定或源非 EPSG:3857，重投影到 EPSG:3857。

    返回切片时使用的输入路径（原始或重投影产物）。
    """
    if not force_reproject:
        # 检查源 CRS
        try:
            info = subprocess.run(
                ["gdalinfo", str(tif_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (info.stdout or "") + (info.stderr or "")
            normalized = output.replace('"', '').replace(' ', '')
            if "EPSG:3857" in normalized or "Pseudo-Mercator" in output or "ID[EPSG,3857]" in normalized:
                print("[OK] 源 TIF 已是 EPSG:3857，跳过重投影。")
                return tif_path
        except subprocess.SubprocessError:
            pass

    warped = work_dir / "warped_3857.tif"
    if warped.exists():
        print(f"[OK] 重投影产物已存在，复用：{warped}")
        return warped

    print(f"[INFO] 重投影到 EPSG:3857：{tif_path} → {warped}")
    cmd = [
        "gdalwarp",
        "-t_srs",
        "EPSG:3857",
        "-r",
        "average",
        "-co",
        "TILED=YES",
        "-co",
        "COMPRESS=LZW",
        str(tif_path),
        str(warped),
    ]
    subprocess.run(cmd, check=True)
    return warped


def _run_gdal2tiles(
    input_tif: Path,
    out_dir: Path,
    zoom: str,
    processes: int,
) -> None:
    """调用 gdal2tiles 生成 XYZ 瓦片金字塔。"""
    cmd = [
        "gdal2tiles",
        "--xyz",
        f"--zoom={zoom}",
        "--resampling=average",
        f"--processes={processes}",
        "--webviewer=none",  # 不生成 HTML 查看器
        "-n",  # 不生成 KML
        "-x",  # 排除透明瓦片
        "-v",  # 输出进度
        str(input_tif),
        str(out_dir),
    ]
    print("[INFO] 执行 gdal2tiles：" + " ".join(cmd))
    start = time.time()
    subprocess.run(cmd, check=True)
    print(f"[OK] gdal2tiles 完成，耗时 {time.time() - start:.1f}s")


def _print_stats(out_dir: Path) -> None:
    """输出切片统计：层级数、瓦片总数、占用空间。"""
    zoom_levels = []
    total_tiles = 0
    for z_dir in sorted(out_dir.iterdir()):
        if not z_dir.is_dir() or not z_dir.name.isdigit():
            continue
        z = int(z_dir.name)
        count = sum(1 for _ in z_dir.rglob("*.png"))
        zoom_levels.append((z, count))
        total_tiles += count

    total_bytes = sum(f.stat().st_size for f in out_dir.rglob("*.png"))
    total_mb = total_bytes / (1024 * 1024)

    print("\n===== 切片统计 =====")
    for z, n in zoom_levels:
        print(f"  zoom {z}: {n:>6} 张瓦片")
    print(f"  合计：{len(zoom_levels)} 个层级，{total_tiles} 张瓦片，{total_mb:.1f} MB")
    print("====================")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将源 GeoTIFF 切片为 XYZ 瓦片金字塔（Leaflet 兼容）"
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE_TIF,
        help=f"源 TIF 路径（默认：{DEFAULT_SOURCE_TIF}）",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"输出目录（默认：{DEFAULT_OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--zoom",
        default=DEFAULT_ZOOM,
        help=f"zoom 范围，格式 'min-max'（默认：{DEFAULT_ZOOM}）",
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=DEFAULT_PROCESSES,
        help=f"并行进程数（默认：{DEFAULT_PROCESSES}）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="清理已有输出目录后重建",
    )
    parser.add_argument(
        "--reproject",
        action="store_true",
        help="强制重投影到 EPSG:3857（源非 3857 时使用，默认源已是 3857 时跳过）",
    )
    args = parser.parse_args()

    _setup_gdal_env()
    _check_gdal()

    tif_path = Path(args.source)
    out_dir = Path(args.output)
    _check_source(tif_path)
    _prepare_output(out_dir, args.force)

    input_for_tiling = _reproject_if_needed(tif_path, args.reproject, out_dir.parent)
    _run_gdal2tiles(input_for_tiling, out_dir, args.zoom, args.processes)
    _print_stats(out_dir)

    print("\n[DONE] 切片完成。前端可通过 /tiles/{z}/{x}/{y}.png 加载底图。")


if __name__ == "__main__":
    main()

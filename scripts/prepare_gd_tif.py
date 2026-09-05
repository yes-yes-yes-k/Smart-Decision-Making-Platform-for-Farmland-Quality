"""广东 100m TIF 预处理：Float64 Gray → Byte RGB + 色调匹配。

将源 Float64 灰度 TIF（ColorInterp=Gray/Undefined）归一化为 Byte RGB TIF，
使色调与全国基准 TIF（China_RGB_500m_vis.tif）对齐，供 gdal2tiles 切片。

流水线：
  1. gdal_edit.py -colorinterp 修正波段颜色解释为 R/G/B（原地修改元数据）
  2. 默认：rasterio + scikit-image 直方图匹配到基准 TIF
     回退：gdal_translate -ot Byte -scale 0 2000 0 255（2% 截断线性拉伸）

环境依赖：
  - GDAL >= 3.5（gdal_edit.py / gdal_translate）
  - Python: rasterio + scikit-image（直方图匹配，可选；缺失时自动降级）

使用：
  python scripts/prepare_gd_tif.py                              # 默认直方图匹配
  python scripts/prepare_gd_tif.py --no-match-base             # 2% 截断线性拉伸
  python scripts/prepare_gd_tif.py --source <path> --output <path>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认路径
DEFAULT_SOURCE_TIF = r"E:\Agent\一张图地图\China_RGB_500m_vis\Guangdong_RGB_100m\Guangdong_RGB_100m.tif"
DEFAULT_BASE_TIF = r"E:\Agent\一张图地图\China_RGB_500m_vis\China_RGB_500m_vis.tif"
DEFAULT_OUTPUT_TIF = _PROJECT_ROOT / "data" / "gd_tif_normalized.tif"

# 2% 截断线性拉伸参数（基于源数据统计：99% 像素集中在 0-2000）
FALLBACK_SCALE_MAX = 2000

_MINIFORGE_ROOT = Path(r"C:\Users\Karry\miniforge3")


def _setup_gdal_env() -> None:
    """将 Miniforge3 的 GDAL bin 与 GDAL_DATA 加入环境。"""
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
    """校验 GDAL 可用性；不可用时打印安装指引并退出。"""
    try:
        result = subprocess.run(
            ["gdalinfo", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise FileNotFoundError("gdalinfo 返回非零")
        version_line = (result.stdout or result.stderr or "").strip().splitlines()[0]
        print(f"[OK] GDAL 可用：{version_line}")
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(
            "[FAIL] 未找到 gdalinfo 命令。请安装 GDAL：\n"
            "  推荐（Windows）：安装 Miniforge3 后执行\n"
            "    conda install -c conda-forge gdal\n"
            "  或安装 OSGeo4W64 并勾选 gdal 包。\n"
            f"  错误详情：{e}",
            file=sys.stderr,
        )
        sys.exit(2)


def _check_source(tif_path: Path) -> None:
    """校验源 TIF 存在性 + 坐标系为 EPSG:3857。"""
    if not tif_path.exists():
        print(f"[FAIL] 源 TIF 不存在：{tif_path}", file=sys.stderr)
        sys.exit(3)
    size_mb = tif_path.stat().st_size / (1024 * 1024)
    print(f"[OK] 源 TIF：{tif_path}（{size_mb:.1f} MB）")

    # 校验坐标系
    try:
        info = subprocess.run(
            ["gdalinfo", str(tif_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (info.stdout or "") + (info.stderr or "")
        normalized = output.replace('"', '').replace(' ', '')
        if not ("EPSG:3857" in normalized or "Pseudo-Mercator" in output or "ID[EPSG,3857]" in normalized):
            print(f"[FAIL] 源 TIF 坐标系非 EPSG:3857，无法直接切片。请先重投影。", file=sys.stderr)
            sys.exit(3)
        print("[OK] 源 TIF 坐标系：EPSG:3857")
    except subprocess.SubprocessError as e:
        print(f"[WARN] 无法校验坐标系（gdalinfo 失败）：{e}", file=sys.stderr)


def _fix_colorinterp(tif_path: Path) -> None:
    """用 GDAL Python 绑定原地修正波段颜色解释为 R/G/B。

    接受任意 TIF（源或输出）。对输出 TIF 调用可避免源 COG 布局限制。
    """
    try:
        from osgeo import gdal
    except ImportError as e:
        print(f"[WARN] 无法导入 osgeo.gdal：{e}，跳过 ColorInterp 修正")
        print("[WARN] 后续 gdal_translate 仍会处理，但 ColorInterp 可能保持 Gray")
        return

    gdal.UseExceptions()
    GCI_mappings = {
        1: gdal.GCI_RedBand,
        2: gdal.GCI_GreenBand,
        3: gdal.GCI_BlueBand,
    }
    band_names = {1: "Red", 2: "Green", 3: "Blue"}

    print(f"[INFO] 修正 ColorInterp 为 R/G/B：{tif_path}")
    # 用 IGNORE_COG_LAYOUT_BREAK=YES 打开，避免 COG 布局限制
    ds = gdal.OpenEx(
        str(tif_path),
        gdal.OF_RASTER | gdal.GA_Update,
        open_options=["IGNORE_COG_LAYOUT_BREAK=YES"],
    )
    if ds is None:
        print(f"[FAIL] 无法以读写模式打开 TIF：{tif_path}", file=sys.stderr)
        return

    success = True
    for band_idx, color_interp in GCI_mappings.items():
        band = ds.GetRasterBand(band_idx)
        if band is None:
            print(f"[WARN] 波段 {band_idx} 不存在")
            success = False
            continue
        err = band.SetRasterColorInterpretation(color_interp)
        if err != 0:
            print(f"[WARN] 波段 {band_idx} ColorInterp 设置失败")
            success = False
        else:
            print(f"  Band {band_idx} → {band_names[band_idx]}")

    ds.FlushCache()
    ds = None  # 释放文件句柄
    if success:
        print("[OK] ColorInterp 已修正为 Red/Green/Blue")
    else:
        print("[WARN] ColorInterp 部分修正失败，继续后续步骤")


def _histogram_match(source_tif: Path, base_tif: Path, output_tif: Path) -> bool:
    """用 rasterio + scikit-image 对三波段做直方图匹配到基准 TIF。

    成功返回 True，失败返回 False（调用方负责降级）。
    """
    try:
        import rasterio
        from skimage.exposure import match_histograms
        import numpy as np
    except ImportError as e:
        print(f"[WARN] 直方图匹配依赖缺失（{e}），将降级到线性拉伸")
        return False

    print(f"[INFO] 加载基准 TIF：{base_tif}")
    try:
        with rasterio.open(base_tif) as base_ds:
            base_data = base_ds.read().astype(np.float32)  # (3, H, W)
        print(f"[OK] 基准 TIF 加载完成：{base_data.shape}")
    except Exception as e:
        print(f"[WARN] 基准 TIF 加载失败：{e}")
        return False

    print(f"[INFO] 加载源 TIF：{source_tif}")
    try:
        with rasterio.open(source_tif) as src_ds:
            src_data = src_ds.read().astype(np.float32)  # (3, H, W)
            profile = src_ds.profile.copy()
        print(f"[OK] 源 TIF 加载完成：{src_data.shape}")
    except Exception as e:
        print(f"[WARN] 源 TIF 加载失败：{e}")
        return False

    print("[INFO] 执行三波段直方图匹配...")
    matched = np.zeros_like(src_data, dtype=np.uint8)
    for band_idx in range(3):
        matched[band_idx] = match_histograms(
            src_data[band_idx],
            base_data[band_idx],
        ).astype(np.uint8)
        print(f"  Band {band_idx + 1} 匹配完成")

    # 更新 profile
    profile.update(dtype="uint8", count=3)
    # 确保 colorinterp 正确
    profile.setdefault("colorinterp", [3, 2, 1])  # 3=Red, 2=Green, 1=Blue

    print(f"[INFO] 写入归一化 TIF：{output_tif}")
    output_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_tif, "w", **profile) as dst:
        dst.write(matched)
    # ColorInterp 由后续 _fix_colorinterp(output_tif) 统一设置（用 GDAL Python 绑定）

    print(f"[OK] 直方图匹配完成，输出：{output_tif}")
    return True


def _linear_stretch(source_tif: Path, output_tif: Path, scale_max: int) -> None:
    """用 gdal_translate 做 2% 截断线性拉伸 Float64→Byte。"""
    output_tif.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gdal_translate",
        "-ot", "Byte",
        "-scale", "0", str(scale_max), "0", "255",
        "-of", "GTiff",
        "-co", "TILED=YES",
        "-co", "BLOCKXSIZE=256",
        "-co", "BLOCKYSIZE=256",
        "-co", "COMPRESS=LZW",
        str(source_tif),
        str(output_tif),
    ]
    print(f"[INFO] 执行线性拉伸（scale_max={scale_max}）：{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        print(f"[FAIL] gdal_translate 失败：{result.stderr}", file=sys.stderr)
        sys.exit(5)
    print(f"[OK] 线性拉伸完成，输出：{output_tif}")


def _print_stats(source_tif: Path, output_tif: Path, used_histogram: bool) -> None:
    """打印处理统计：源大小、输出大小、各波段统计值变化。"""
    src_mb = source_tif.stat().st_size / (1024 * 1024)
    out_mb = output_tif.stat().st_size / (1024 * 1024) if output_tif.exists() else 0
    print("\n===== 预处理统计 =====")
    print(f"  源 TIF: {src_mb:.1f} MB ({source_tif.name})")
    print(f"  输出 TIF: {out_mb:.1f} MB ({output_tif.name})")
    print(f"  色调处理: {'直方图匹配（推荐）' if used_histogram else '2% 截断线性拉伸（回退）'}")

    # 输出 TIF 波段统计
    try:
        info = subprocess.run(
            ["gdalinfo", "-stats", str(output_tif)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = info.stdout or ""
        for line in output.splitlines():
            if "ColorInterp" in line or "Type=" in line:
                print(f"  {line.strip()}")
    except subprocess.SubprocessError:
        pass
    print("====================")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="广东 100m TIF 预处理：Float64 Gray → Byte RGB + 色调匹配"
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE_TIF,
        help=f"源 TIF 路径（默认：{DEFAULT_SOURCE_TIF}）",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE_TIF,
        help=f"基准 TIF 路径（直方图匹配用，默认：{DEFAULT_BASE_TIF}）",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_TIF),
        help=f"输出 TIF 路径（默认：{DEFAULT_OUTPUT_TIF}）",
    )
    parser.add_argument(
        "--no-match-base",
        action="store_true",
        help="禁用直方图匹配，回退到 2%% 截断线性拉伸",
    )
    parser.add_argument(
        "--scale-max",
        type=int,
        default=FALLBACK_SCALE_MAX,
        help=f"线性拉伸上限（默认：{FALLBACK_SCALE_MAX}，仅 --no-match-base 或降级时使用。默认值 2000 对应 2%% 截断）",
    )
    args = parser.parse_args()

    _setup_gdal_env()
    _check_gdal()

    source_tif = Path(args.source)
    base_tif = Path(args.base)
    output_tif = Path(args.output)

    _check_source(source_tif)
    if not base_tif.exists():
        print(f"[WARN] 基准 TIF 不存在：{base_tif}，将降级到线性拉伸")
        args.no_match_base = True

    # 第一步：色调处理（类型转换 + 拉伸/匹配）
    used_histogram = False
    if not args.no_match_base:
        print("[INFO] 尝试直方图匹配（默认推荐）...")
        used_histogram = _histogram_match(source_tif, base_tif, output_tif)
        if not used_histogram:
            print("[WARN] 直方图匹配失败，降级到 2% 截断线性拉伸")
            _linear_stretch(source_tif, output_tif, args.scale_max)
    else:
        print("[INFO] 跳过直方图匹配，使用 2% 截断线性拉伸")
        _linear_stretch(source_tif, output_tif, args.scale_max)

    # 第二步：修正 ColorInterp（对输出 TIF 操作，避免源 COG 布局限制）
    _fix_colorinterp(output_tif)

    # 打印统计
    _print_stats(source_tif, output_tif, used_histogram)

    print("\n[DONE] 预处理完成。可执行切片：")
    print(f"  python scripts/generate_basemap_tiles.py --source {output_tif} --output data/gd_basemap_tiles --zoom 4-11 --force")


if __name__ == "__main__":
    main()

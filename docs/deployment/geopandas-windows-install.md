# GeoPandas Windows 安装说明

GeoPandas 在 Windows 上的安装比 Linux/macOS 复杂，因为它依赖 GDAL、PROJ、GEOS 等 C 库。本文档记录两种可行安装方式。

## 前置条件

- Python 3.11+（当前验证环境为 Python 3.12）
- pip 或 conda

## 方式一：conda 安装（推荐）

conda 会自动安装 GDAL/PROJ/GEOS 等 C 依赖，是最简单可靠的方式。

```bash
# 安装 miniconda（如未安装）
# 下载地址：https://docs.conda.io/en/latest/miniconda.html

# 创建环境并安装
conda create -n ai_culti python=3.12
conda activate ai_culti

# 一次安装所有依赖
conda install -c conda-forge geopandas scipy
```

验证：

```bash
python -c "import geopandas; print(geopandas.__version__)"
```

## 方式二：pip + 预编译 wheel 安装

无法使用 conda 时，通过 pip 安装预编译 wheel。关键在于先安装带 C 库的依赖包（GDAL/Fiona/pyproj/Shapely），再安装 geopandas。

### 步骤 1：安装 C 库依赖

使用 Christoph Gohlke 发布的预编译 wheel（Windows 二进制）：

```powershell
# 仅 Windows：先升级 pip
python -m pip install --upgrade pip

# 安装 pyproj（PROJ 绑定）
pip install pyproj

# 安装 Shapely（GEOS 绑定）
pip install shapely

# 安装 Fiona（OGR 绑定，GDAL）
pip install fiona
```

若 pip 安装 Fiona 失败（常见于新版 Python），从 https://www.lfd.uci.edu/~gohlke/pythonlibs/ 下载对应 wheel：

```powershell
# 示例：Python 3.12 + Windows 64 位
pip install Fiona-1.9.6-cp312-cp312-win_amd64.whl
```

### 步骤 2：安装 geopandas 和 scipy

```powershell
pip install geopandas scipy
```

### 步骤 3：验证

```powershell
python -c "import geopandas as gpd; print('geopandas', gpd.__version__); import scipy; print('scipy', scipy.__version__)"
```

期望输出：

```
geopandas 0.14.x
scipy 1.11.x
```

## 常见问题

### 1. `ImportError: DLL load failed while importing _fiona`

Fiona 找不到 GDAL DLL。解决：

- 确认 GDAL 已安装（`gdalinfo --version`）
- 将 GDAL 的 bin 目录加入 PATH
- 或改用 conda 安装

### 2. `ERROR: Could not build wheels for fiona`

缺少 C 编译器。解决：

- 使用预编译 wheel（见方式二步骤 1）
- 或安装 Build Tools for Visual Studio 后重试

### 3. shapefile 读取中文乱码

GeoPandas 默认使用 UTF-8 编码。若 shapefile 使用 GBK 编码：

```python
import geopandas as gpd
gdf = gpd.read_file("data/farmland_stability/2018_测试数据.shp", encoding='gbk')
```

### 4. proj.db 找不到

PROJ 数据库路径未配置。设置环境变量：

```powershell
$env:PROJ_LIB = "C:\path\to\proj\share"
```

conda 安装通常自动配置。

## 项目中的使用

模型1（耕地质量稳定性与退化风险）通过 geopandas 读取 3 期 shapefile：

```python
import geopandas as gpd

G = gpd.read_file("data/farmland_stability/2018_测试数据.shp")
H = [gpd.read_file(f"data/farmland_stability/{y}_测试数据.shp") for y in ["2021","2024"]]
```

若 geopandas 不可用，模型1 模块会触发 ImportError，MODEL_SPECS 中 `STABILITY_MODEL_AVAILABLE = False`，相关 agent 自动回退到模拟数据。

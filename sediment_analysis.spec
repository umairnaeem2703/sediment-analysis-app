# -*- mode: python ; coding: utf-8 -*-
# Onedir Windows build (preferred over onefile for NumPy/MKL):
#   pyinstaller --noconfirm sediment_analysis.spec
# Do not collect pytest. Do not add rasterio/GDAL.

from PyInstaller.utils.hooks import collect_all

datas_mpl, binaries_mpl, hidden_mpl = collect_all("matplotlib")
datas_np, binaries_np, hidden_np = collect_all("numpy")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries_mpl + binaries_np,
    datas=datas_mpl + datas_np + [("inputs", "inputs")],
    hiddenimports=list(
        set(
            hidden_mpl
            + hidden_np
            + [
                "matplotlib.backends.backend_tkagg",
                "matplotlib.backends.backend_agg",
                "openpyxl",
                "PIL",
                "PIL.TiffImagePlugin",
            ]
        )
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "rasterio", "osgeo", "gdal"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SedimentAnalysis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SedimentAnalysis",
)

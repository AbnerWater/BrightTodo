# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for LifeTrace backend
Creates a one-folder bundle (recommended for large dependencies like PyTorch)
"""

import os
import shutil
import sys
from pathlib import Path

# Try to get the directory from SPECPATH (set by PyInstaller)
try:
    # SPECPATH is automatically set by PyInstaller to the spec file's absolute path
    spec_path = Path(SPECPATH)
    lifetrace_dir = spec_path.resolve().parent
except (NameError, AttributeError):
    # Fallback: use current working directory (should be lifetrace dir when script runs)
    lifetrace_dir = Path(os.getcwd()).resolve()

# Verify the directory contains the expected structure
config_file = lifetrace_dir / "config" / "default_config.yaml"
if not config_file.exists():
    # If config not found, try going up one level to find lifetrace directory
    # This handles the case where we're in a subdirectory
    potential_lifetrace = lifetrace_dir.parent / "lifetrace"
    if (potential_lifetrace / "config" / "default_config.yaml").exists():
        lifetrace_dir = potential_lifetrace
    else:
        # Last resort: try to find it relative to current working directory
        cwd = Path(os.getcwd())
        if (cwd / "config" / "default_config.yaml").exists():
            lifetrace_dir = cwd
        elif (cwd / "lifetrace" / "config" / "default_config.yaml").exists():
            lifetrace_dir = cwd / "lifetrace"

# Final verification - raise error if still not found
if not (lifetrace_dir / "config" / "default_config.yaml").exists():
    raise FileNotFoundError(
        f"Cannot find config file. Tried: {lifetrace_dir / 'config' / 'default_config.yaml'}\n"
        f"SPECPATH: {SPECPATH if 'SPECPATH' in globals() else 'not set'}\n"
        f"CWD: {os.getcwd()}\n"
        f"Please ensure you run PyInstaller from the lifetrace directory or specify the correct path."
    )

def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# Build options (override with env vars if needed)
# LIFETRACE_INCLUDE_VECTOR=1 to include vector deps (chromadb/transformers/torch/etc.)
include_vector = _env_flag("LIFETRACE_INCLUDE_VECTOR", False)
optimize_level = _env_int("PYINSTALLER_OPTIMIZE", 1)
enable_strip = _env_flag("PYINSTALLER_STRIP", sys.platform != "win32")
enable_upx = _env_flag(
    "PYINSTALLER_UPX",
    bool(shutil.which("upx")) and sys.platform != "darwin",
)

# Data files to include
# 注意：config 和 models 放在 app 根目录（与 _internal 同级别），而不是 _internal 内
# 这样在打包环境中，路径为 backend/config/ 和 backend/models/
datas = [
    # Configuration files - 放在 app 根目录下的 config/
    (str(lifetrace_dir / "config" / "default_config.yaml"), "config"),
    (str(lifetrace_dir / "config" / "rapidocr_config.yaml"), "config"),
    # Prompts directory - 包含所有拆分后的 prompt yaml 文件
    (str(lifetrace_dir / "config" / "prompts"), "config/prompts"),
    # ONNX model files - 放在 app 根目录下的 models/
    (str(lifetrace_dir / "models" / "ch_PP-OCRv4_det_infer.onnx"), "models"),
    (str(lifetrace_dir / "models" / "ch_PP-OCRv4_rec_infer.onnx"), "models"),
    (str(lifetrace_dir / "models" / "ch_ppocr_mobile_v2.0_cls_infer.onnx"), "models"),
]

# Hidden imports (modules that PyInstaller might miss)
# 注意：这些模块需要与 pyproject.toml 中的依赖保持一致
hiddenimports = [
    # LifeTrace core modules
    "lifetrace",
    "lifetrace.server",
    "lifetrace.util",
    "lifetrace.util.config",
    "lifetrace.util.logging_config",
    "lifetrace.routers",
    "lifetrace.storage",
    "lifetrace.llm",
    "lifetrace.jobs",
    "lifetrace.schemas",
    "lifetrace.services",
    # FastAPI and web server (fastapi, uvicorn)
    "fastapi",
    "uvicorn",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "jinja2",  # FastAPI 依赖
    # Data validation and ORM (pydantic, sqlalchemy, sqlmodel, alembic)
    "pydantic",
    "pydantic.json",
    "sqlalchemy",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.dialects.sqlite",
    "sqlmodel",
    "alembic",
    "alembic.config",
    "alembic.script",
    "alembic.runtime",
    "alembic.runtime.environment",
    "alembic.runtime.migration",
    # Screenshot and image processing (mss, Pillow, imagehash)
    "mss",
    "PIL",
    "PIL.Image",
    "imagehash",
    "cv2",  # rapidocr 依赖
    "numpy",
    "numpy._core",
    "numpy._core._multiarray_umath",
    "numpy._core.multiarray",
    "numpy._core.umath",
    "numpy._globals",
    "numpy._core._globals",
    # OCR processing (rapidocr-onnxruntime)
    "rapidocr_onnxruntime",
    "rapidocr_onnxruntime.main",
    "rapidocr_onnxruntime.cal_rec_boxes",
    "rapidocr_onnxruntime.ch_ppocr_cls",
    "rapidocr_onnxruntime.ch_ppocr_det",
    "rapidocr_onnxruntime.ch_ppocr_rec",
    "rapidocr_onnxruntime.utils",
    # Configuration (pyyaml, dynaconf)
    "yaml",
    "dynaconf",
    "dynaconf.loaders",
    "dynaconf.loaders.yaml_loader",
    "dynaconf.utils",
    "dynaconf.utils.boxing",
    "dynaconf.utils.parse_conf",
    "dynaconf.validator",
    # Scheduler (apscheduler)
    "apscheduler",
    "apscheduler.executors",
    "apscheduler.executors.pool",
    "apscheduler.jobstores",
    "apscheduler.jobstores.memory",
    "apscheduler.triggers",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.interval",
    # Utils (psutil, openai, tavily)
    "psutil",
    "openai",
    "tavily",  # Tavily API for web search
    "dateutil",  # 可能被其他库依赖
    "rich",  # 可能被其他库依赖
    # Logging (loguru)
    "loguru",
    "loguru._defaults",
    "loguru._handler",
    "loguru._logger",
    "loguru._recattrs",
    "loguru._file_sink",
    "loguru._colorizer",
    "loguru._contextvars",
    "loguru._get_frame",
    "loguru._simple_sink",
    "loguru._string_parsers",
    "loguru._writer",
    # Vector database and semantic search (可选 vector 组) - 按需添加
]

# 平台特定的 hidden imports
if sys.platform == "darwin":
    # macOS specific (pyobjc-framework-Cocoa, pyobjc-framework-Quartz)
    hiddenimports.extend([
        "objc",
        "AppKit",
        "Cocoa",
        "Quartz",
        "Quartz.CoreGraphics",
        "CoreFoundation",
    ])
elif sys.platform == "win32":
    # Windows specific (pywin32)
    hiddenimports.extend([
        "win32api",
        "win32con",
        "win32gui",
        "win32process",
        "pywintypes",
    ])

# Collect all lifetrace source files to ensure they're included
# PyInstaller needs the parent directory in pathex to find the lifetrace module
lifetrace_parent_dir = str(lifetrace_dir.parent)

# Collect data files and binaries from rapidocr_onnxruntime package
# This ensures config.yaml and other data files are included
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all submodules to ensure nothing is missed
rapidocr_submodules = collect_submodules("rapidocr_onnxruntime")
hiddenimports.extend(rapidocr_submodules)

# Collect data files (config.yaml, etc.)
rapidocr_datas = collect_data_files("rapidocr_onnxruntime")
datas.extend(rapidocr_datas)

# Collect all chromadb submodules (including telemetry.product.posthog)
# ChromaDB and sentence-transformers are optional; include only if enabled
vector_modules = [
    "torch",
    "torchvision",
    "torchaudio",
    "transformers",  # sentence-transformers 依赖
    "scipy",
    "hdbscan",
    "sentence_transformers",
    "chromadb",
]
if include_vector:
    hiddenimports.extend(vector_modules)
    chromadb_submodules = collect_submodules("chromadb")
    hiddenimports.extend(chromadb_submodules)
    chromadb_datas = collect_data_files("chromadb")
    datas.extend(chromadb_datas)

    sentence_transformers_submodules = collect_submodules("sentence_transformers")
    hiddenimports.extend(sentence_transformers_submodules)
    sentence_transformers_datas = collect_data_files("sentence_transformers")
    datas.extend(sentence_transformers_datas)

# Collect dynaconf submodules and data files (配置管理)
dynaconf_submodules = collect_submodules("dynaconf")
hiddenimports.extend(dynaconf_submodules)
dynaconf_datas = collect_data_files("dynaconf")
datas.extend(dynaconf_datas)

# Collect sqlmodel submodules (ORM)
sqlmodel_submodules = collect_submodules("sqlmodel")
hiddenimports.extend(sqlmodel_submodules)

# Collect alembic submodules and data files (数据库迁移)
alembic_submodules = collect_submodules("alembic")
hiddenimports.extend(alembic_submodules)
alembic_datas = collect_data_files("alembic")
datas.extend(alembic_datas)

# Collect imagehash submodules (图像哈希)
imagehash_submodules = collect_submodules("imagehash")
hiddenimports.extend(imagehash_submodules)

# Collect tavily submodules (Tavily API for web search)
tavily_submodules = collect_submodules("tavily")
hiddenimports.extend(tavily_submodules)

# Collect tavily data files if any
tavily_datas = collect_data_files("tavily")
datas.extend(tavily_datas)

# Collect numpy submodules (NumPy 2.x 需要显式收集子模块)
# NumPy 2.4+ 与 PyInstaller 的兼容性问题，需要确保所有核心模块都被包含
numpy_submodules = collect_submodules("numpy")
hiddenimports.extend(numpy_submodules)
# 特别添加 numpy._core 和 numpy._globals 相关模块
numpy_core_submodules = collect_submodules("numpy._core")
hiddenimports.extend(numpy_core_submodules)

excludes = [
    "matplotlib",
    "tkinter",
    "pytest",
    # 注意：不要排除 unittest，因为 imagehash 等库可能依赖它
    # "unittest",
    "test",
    "tests",
]
if not include_vector:
    excludes.extend(vector_modules)

a = Analysis(
    ["scripts/start_backend.py"],
    pathex=[lifetrace_parent_dir, str(lifetrace_dir)],  # Add both parent and lifetrace directory to Python path
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=optimize_level,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lifetrace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=enable_strip,
    upx=enable_upx,
    console=True,  # Keep console for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=enable_strip,
    upx=enable_upx,
    upx_exclude=[],
    name="lifetrace",
)

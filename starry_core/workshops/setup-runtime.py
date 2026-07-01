#!/usr/bin/env python3
"""
Starry Space - Runtime Setup Script
=====================================
自动下载并配置跨平台运行时环境。

核心职责：
    1. 下载 uv 二进制（macOS / Linux，双架构）。
    2. 下载 Windows 嵌入式 Python 3.13.14。
    3. 在当前运行平台（macOS / Linux）上，使用 uv 安装统一版本
       Python 3.13.14 到 runtime/python-cache/。
    4. 校验并打印最终可用的 Python 路径。

Usage:
    python starry_core/tools/setup-runtime.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# ═══════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════

UV_VERSION = "0.11.25"
PYTHON_VERSION = "3.13.14"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
CACHE_DIR = BASE_DIR / ".cache" / "downloads"
PYTHON_CACHE_DIR = RUNTIME_DIR / "python-cache"

DOWNLOADS = {
    "uv-macos-aarch64": {
        "url": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-aarch64-apple-darwin.tar.gz",
        "archive": "uv-aarch64-apple-darwin.tar.gz",
        "extract_to": RUNTIME_DIR / "macOS",
        "final_name": "uv-aarch64",
        "platform": "macOS (Apple Silicon)",
    },
    "uv-macos-x86_64": {
        "url": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-apple-darwin.tar.gz",
        "archive": "uv-x86_64-apple-darwin.tar.gz",
        "extract_to": RUNTIME_DIR / "macOS",
        "final_name": "uv-x86_64",
        "platform": "macOS (Intel)",
    },
    "uv-linux-x86_64": {
        "url": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz",
        "archive": "uv-x86_64-unknown-linux-gnu.tar.gz",
        "extract_to": RUNTIME_DIR / "linux",
        "final_name": "uv-x86_64",
        "platform": "Linux (x64)",
    },
    "uv-linux-aarch64": {
        "url": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-aarch64-unknown-linux-gnu.tar.gz",
        "archive": "uv-aarch64-unknown-linux-gnu.tar.gz",
        "extract_to": RUNTIME_DIR / "linux",
        "final_name": "uv-aarch64",
        "platform": "Linux (ARM64)",
    },
    "python-embed-windows": {
        "url": f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip",
        "archive": f"python-{PYTHON_VERSION}-embed-amd64.zip",
        "extract_to": RUNTIME_DIR / "windows" / "python_embed",
        "final_name": None,
        "platform": "Windows (x64)",
    },
}


# ═══════════════════════════════════════════════════════
# 平台工具函数
# ═══════════════════════════════════════════════════════

def get_current_platform() -> tuple[str, str]:
    """返回 (system, arch)，system 统一为 windows / macOS / linux。"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        system = "macos"
    elif system == "windows":
        system = "windows"
    elif system.startswith("linux"):
        system = "linux"

    if machine in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "aarch64"
    else:
        arch = machine

    # Windows 嵌入式 Python 只提供 amd64，这里统一视为 x86_64
    if system == "windows":
        arch = "x86_64"

    return system, arch


def get_uv_path(system: str, arch: str) -> Path:
    """返回指定平台架构对应的 uv 二进制路径。"""
    # 目录名保持与现有目录一致：macOS / linux / windows
    dir_name = "macOS" if system == "macos" else system
    return RUNTIME_DIR / dir_name / f"uv-{arch}"


def normalize_system_dir(system: str) -> str:
    """把 system 名称映射到项目目录名。"""
    return "macOS" if system == "macos" else system


# ═══════════════════════════════════════════════════════
# 通用工具函数
# ═══════════════════════════════════════════════════════

def print_header(text: str) -> None:
    print(f"\n{'='*56}")
    print(f"  {text}")
    print(f"{'='*56}")


def download_file(url: str, dest: Path, name: str) -> bool:
    if dest.exists():
        size = dest.stat().st_size
        print(f"  Cached: {name} ({size/1024/1024:.1f} MB)")
        return True

    print(f"  Downloading {name}...")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        size = dest.stat().st_size
        print(f"  Done ({size/1024/1024:.1f} MB)")
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def find_file_in_dir(directory: Path, filename: str) -> Path | None:
    """递归在目录中查找指定文件。"""
    for item in directory.rglob("*"):
        if item.is_file() and item.name == filename:
            return item
    return None


def find_any_file_in_dir(directory: Path) -> Path | None:
    """递归查找第一个文件。"""
    for item in directory.rglob("*"):
        if item.is_file():
            return item
    return None


def extract_archive(archive_path: Path, extract_to: Path, is_zip: bool = False) -> None:
    extract_to.mkdir(parents=True, exist_ok=True)
    if is_zip:
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_to)
    else:
        with tarfile.open(archive_path, "r:gz") as t:
            t.extractall(extract_to)


# ═══════════════════════════════════════════════════════
# 安装逻辑
# ═══════════════════════════════════════════════════════

def setup_uv(name: str, config: dict) -> bool:
    print(f"\n[{config['platform']}]")

    # 1. 下载
    archive_path = CACHE_DIR / config["archive"]
    if not download_file(config["url"], archive_path, config["archive"]):
        return False

    # 2. 解压到临时目录
    temp_extract = CACHE_DIR / f"extract_{name}"
    if temp_extract.exists():
        shutil.rmtree(temp_extract)
    temp_extract.mkdir(parents=True, exist_ok=True)

    is_zip = config["archive"].endswith(".zip")
    extract_archive(archive_path, temp_extract, is_zip=is_zip)

    # 3. 找到解压出的 uv 二进制（tar.gz 解压后可能多一层子目录）
    extracted_uv = find_file_in_dir(temp_extract, "uv")
    if not extracted_uv:
        extracted_uv = find_any_file_in_dir(temp_extract)

    if not extracted_uv or not extracted_uv.exists():
        print(f"  Error: Could not find 'uv' binary in extracted files")
        print(f"  Extracted to: {temp_extract}")
        for item in temp_extract.rglob("*"):
            print(f"    {item.relative_to(temp_extract)}")
        return False

    # 4. 复制到最终位置
    final_path = config["extract_to"] / config["final_name"]
    config["extract_to"].mkdir(parents=True, exist_ok=True)

    shutil.copy2(extracted_uv, final_path)
    os.chmod(final_path, 0o755)
    print(f"  Installed: {final_path}")

    # 5. 清理
    shutil.rmtree(temp_extract)
    return True


def setup_python_embed(config: dict) -> bool:
    print(f"\n[{config['platform']}]")

    archive_path = CACHE_DIR / config["archive"]
    if not download_file(config["url"], archive_path, config["archive"]):
        return False

    extract_to = config["extract_to"]
    if extract_to.exists() and any(extract_to.iterdir()):
        print(f"  Already extracted: {extract_to}")
        return True

    print(f"  Extracting...")
    extract_to.mkdir(parents=True, exist_ok=True)
    extract_archive(archive_path, extract_to, is_zip=True)
    print(f"  Done: {extract_to}")
    return True


def setup_python_via_uv() -> bool:
    """使用 uv 在当前平台安装 Python 3.13.14 到 runtime/python-cache/。"""
    system, arch = get_current_platform()

    if system == "windows":
        print("\n[Python via uv]")
        print("  Windows uses embedded Python, no uv install needed.")
        return verify_windows_embed()

    uv_path = get_uv_path(system, arch)
    if not uv_path.exists():
        print(f"\n[Python via uv]")
        print(f"  Error: uv not found at {uv_path}")
        print(f"  Please run option [1] or [2] first to download uv.")
        return False

    print(f"\n[Python via uv - {system} {arch}]")
    print(f"  uv: {uv_path}")
    print(f"  target version: {PYTHON_VERSION}")
    print(f"  install dir: {PYTHON_CACHE_DIR}")

    os.chmod(uv_path, 0o755)
    PYTHON_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(PYTHON_CACHE_DIR)
    # 让 uv 把 Python 安装到项目目录，而不是 ~/.local/share/uv/python

    cmd = [str(uv_path), "python", "install", PYTHON_VERSION]
    print(f"  Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            check=False,
            text=True,
            timeout=600,
        )
    except Exception as e:
        print(f"  Error running uv: {e}")
        return False

    if result.returncode != 0:
        print(f"  uv exited with code {result.returncode}")
        return False

    print("  uv python install completed.")
    return True


def find_uv_installed_python(system: str, arch: str) -> Path | None:
    """通过 uv python find 定位已安装的 Python。"""
    uv_path = get_uv_path(system, arch)
    if not uv_path.exists():
        return None

    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(PYTHON_CACHE_DIR)

    try:
        result = subprocess.run(
            [str(uv_path), "python", "find", PYTHON_VERSION],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        if result.returncode == 0:
            line = result.stdout.strip().splitlines()[-1].strip()
            candidate = Path(line)
            if candidate.exists():
                return candidate
    except Exception:
        pass

    # fallback：在 python-cache 里搜索 python3 可执行文件
    if PYTHON_CACHE_DIR.exists():
        for item in PYTHON_CACHE_DIR.rglob("python3*"):
            if item.is_file():
                return item
    return None


def verify_python_runtime() -> Path | None:
    """校验当前平台可用的 Python，返回路径或 None。"""
    system, arch = get_current_platform()

    if system == "windows":
        py = RUNTIME_DIR / "windows" / "python_embed" / "python.exe"
        if py.exists():
            print(f"  Found: {py}")
            return py
        print("  Not found: Windows embedded Python")
        return None

    py = find_uv_installed_python(system, arch)
    if py:
        print(f"  Found: {py}")
        return py

    print(f"  Not found: Python {PYTHON_VERSION} in {PYTHON_CACHE_DIR}")
    return None


def verify_windows_embed() -> bool:
    py = RUNTIME_DIR / "windows" / "python_embed" / "python.exe"
    if py.exists():
        print(f"  Found: {py}")
        return True
    print(f"  Not found: {py}")
    return False


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def main() -> None:
    system, arch = get_current_platform()

    print_header("Starry Space - Runtime Setup")
    print(f"UV: {UV_VERSION} | Python: {PYTHON_VERSION}")
    print(f"Root: {BASE_DIR}")
    print(f"Current platform: {system} ({arch})")

    print("\nSelect operation:")
    print("  [1] Setup all runtimes (download binaries + install Python for current platform)")
    print("  [2] Download only (uv binaries + Windows embed, no Python install)")
    print("  [3] Install / verify Python for current platform only")
    print("  [4] Skip")

    choice = input("\nChoice [1]: ").strip() or "1"
    if choice == "4":
        return

    # 下载阶段
    if choice in ("1", "2"):
        print_header("Downloading runtime binaries")

        to_install = []
        to_install.append("python-embed-windows")
        to_install.extend([
            "uv-macos-aarch64",
            "uv-macos-x86_64",
            "uv-linux-x86_64",
            "uv-linux-aarch64",
        ])

        success = []
        failed = []

        for key in to_install:
            config = DOWNLOADS[key]
            if key == "python-embed-windows":
                ok = setup_python_embed(config)
            else:
                ok = setup_uv(key, config)

            if ok:
                success.append(config["platform"])
            else:
                failed.append(config["platform"])

        print_header("Download result")
        if success:
            print("\nOK:")
            for p in success:
                print(f"  {p}")
        if failed:
            print("\nFailed:")
            for p in failed:
                print(f"  {p}")

    # Python 安装阶段
    if choice in ("1", "3"):
        print_header(f"Installing Python {PYTHON_VERSION}")
        ok = setup_python_via_uv()
        if not ok and system != "windows":
            print("\n  Hint: If uv failed, check network / architecture / permissions.")

    # 校验阶段
    print_header("Python runtime verification")
    py = verify_python_runtime()
    if py:
        print("\n  Starry Space runtime is ready.")
        print(f"  Python executable: {py}")
    else:
        print("\n  Starry Space runtime is NOT ready.")
        print("  Run option [1] or [3] to install Python.")

    print(f"\nCache: {CACHE_DIR}")
    print("Delete .cache/ to save space after everything works.")


if __name__ == "__main__":
    main()

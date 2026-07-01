#!/usr/bin/env python3
"""
Starry Space - Bootstrap All Platforms
======================================
在 Windows 上一次性下载所有平台的 Python 3.13.14 缓存：
- Windows x64 / arm64
- Linux x64 / arm64  
- macOS x64 (Intel) / arm64 (Apple Silicon)

Usage:
    python tools/bootstrap-all.py
"""

import os
import sys
import urllib.request
import tarfile
import json
from pathlib import Path

# ═══════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════

VERSION = "3.13.14"
BUILD_DATE = "20260610"  # python-build-standalone release tag
BASE_URL = f"https://github.com/astral-sh/python-build-standalone/releases/download/{BUILD_DATE}"

# 项目目录（脚本在 tools/ 下）
BASE_DIR = Path(__file__).resolve().parent.parent
BOOTSTRAP_DIR = BASE_DIR / "runtime" / "bootstrap"
CACHE_DIR = BASE_DIR / ".cache" / "python-bootstrap"

# 各平台配置
PLATFORMS = {
    "windows-x64": {
        "filename": f"cpython-{VERSION}+{BUILD_DATE}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
        "dir_name": f"cpython-{VERSION}-windows-x86_64-none",
        "size_mb": 21,
    },
    "windows-arm64": {
        "filename": f"cpython-{VERSION}+{BUILD_DATE}-aarch64-pc-windows-msvc-install_only_stripped.tar.gz",
        "dir_name": f"cpython-{VERSION}-windows-aarch64-none",
        "size_mb": 21,
    },
    "linux-x64": {
        "filename": f"cpython-{VERSION}+{BUILD_DATE}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "dir_name": f"cpython-{VERSION}-linux-x86_64-gnu",
        "size_mb": 28,
    },
    "linux-arm64": {
        "filename": f"cpython-{VERSION}+{BUILD_DATE}-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "dir_name": f"cpython-{VERSION}-linux-aarch64-gnu",
        "size_mb": 28,
    },
    "macos-x64": {
        "filename": f"cpython-{VERSION}+{BUILD_DATE}-x86_64-apple-darwin-install_only_stripped.tar.gz",
        "dir_name": f"cpython-{VERSION}-macos-x86_64-none",
        "size_mb": 24,
    },
    "macos-arm64": {
        "filename": f"cpython-{VERSION}+{BUILD_DATE}-aarch64-apple-darwin-install_only_stripped.tar.gz",
        "dir_name": f"cpython-{VERSION}-macos-aarch64-none",
        "size_mb": 24,
    },
}

# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def print_header(text):
    print(f"\n{'='*56}")
    print(f"  {text}")
    print(f"{'='*56}")

def download(url: str, dest: Path, desc: str) -> bool:
    """下载文件，带进度显示"""
    if dest.exists():
        size = dest.stat().st_size / (1024*1024)
        print(f"  [Cached] {desc} ({size:.1f} MB)")
        return True

    print(f"  [Download] {desc}")
    print(f"    From: {url}")

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # 带进度回调
        def report(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                pct = min(downloaded / total_size * 100, 100)
                mb = downloaded / (1024*1024)
                total_mb = total_size / (1024*1024)
                print(f"\r    Progress: {pct:.1f}% ({mb:.1f}/{total_mb:.1f} MB)", end="", flush=True)

        urllib.request.urlretrieve(url, dest, reporthook=report)
        print()  # 换行
        size = dest.stat().st_size / (1024*1024)
        print(f"  [OK] Downloaded ({size:.1f} MB)")
        return True

    except Exception as e:
        print(f"\n  [ERROR] {e}")
        if dest.exists():
            dest.unlink()
        return False

def extract_tarball(tar_path: Path, extract_to: Path, target_dir_name: str):
    """解压 tarball，重命名为统一目录名"""
    import tempfile
    import shutil

    # 创建临时解压目录
    temp_dir = CACHE_DIR / f"extract_{target_dir_name}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [Extract] {tar_path.name}")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(temp_dir)

    # python-build-standalone 解压后通常是 "python/" 或 "install/" 目录
    # 找到实际包含 python 可执行文件的目录
    found = None
    for item in temp_dir.iterdir():
        if item.is_dir():
            # 检查是否包含 python 可执行文件
            if (item / "python.exe").exists() or (item / "bin" / "python3").exists():
                found = item
                break

    if not found:
        # 可能是直接解压到当前目录（没有子目录）
        if (temp_dir / "python.exe").exists() or (temp_dir / "bin" / "python3").exists():
            found = temp_dir

    if not found:
        print(f"  [ERROR] Could not find Python directory in extracted files")
        print(f"  [DEBUG] Contents: {list(temp_dir.iterdir())}")
        return False

    # 移动到最终位置
    final_path = extract_to / target_dir_name
    if final_path.exists():
        print(f"  [INFO] Removing existing {target_dir_name}")
        shutil.rmtree(final_path)

    shutil.copytree(found, final_path)
    print(f"  [OK] Installed to: {final_path}")

    # 清理临时目录
    shutil.rmtree(temp_dir)
    return True

# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def main():
    print_header("Starry Space - Bootstrap All Platforms")
    print(f"Python Version: {VERSION}")
    print(f"Build Date: {BUILD_DATE}")
    print(f"Install Root: {BOOTSTRAP_DIR}")

    # 检查已存在的平台
    existing = []
    missing = []

    BOOTSTRAP_DIR.mkdir(parents=True, exist_ok=True)

    for key, config in PLATFORMS.items():
        target_dir = BOOTSTRAP_DIR / config["dir_name"]
        if target_dir.exists() and any(target_dir.iterdir()):
            existing.append(key)
        else:
            missing.append(key)

    if existing:
        print(f"\n[Already cached] {len(existing)} platforms:")
        for k in existing:
            print(f"  ✓ {k}")

    if not missing:
        print("\n[OK] All platforms already cached!")
        return

    print(f"\n[To download] {len(missing)} platforms:")
    total_mb = sum(PLATFORMS[k]["size_mb"] for k in missing)
    for k in missing:
        print(f"  • {k} (~{PLATFORMS[k]['size_mb']} MB)")
    print(f"\nEstimated total: ~{total_mb} MB")

    confirm = input("\nStart download? [Y/n]: ").strip().lower()
    if confirm and confirm not in ("y", "yes"):
        print("Cancelled.")
        return

    # 开始下载
    print_header("Downloading")
    success = []
    failed = []

    for key in missing:
        config = PLATFORMS[key]
        url = f"{BASE_URL}/{config['filename']}"
        cache_path = CACHE_DIR / config["filename"]

        print(f"\n[{key}]")

        # 1. 下载
        if not download(url, cache_path, config["filename"]):
            failed.append(key)
            continue

        # 2. 解压
        if extract_tarball(cache_path, BOOTSTRAP_DIR, config["dir_name"]):
            success.append(key)
        else:
            failed.append(key)

    # 结果报告
    print_header("Result")

    if success:
        print(f"\n[OK] Successfully installed ({len(success)} platforms):")
        for k in success:
            print(f"  ✓ {k}")

    if failed:
        print(f"\n[Failed] ({len(failed)} platforms):")
        for k in failed:
            print(f"  ✗ {k}")
        print("\nYou can re-run this script to retry.")

    # 显示最终目录
    print("\n[Cache directory]")
    for item in sorted(BOOTSTRAP_DIR.iterdir()):
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) / (1024*1024)
            print(f"  {item.name} ({size:.1f} MB)")

    print(f"\nDownload cache: {CACHE_DIR}")
    print("You can delete .cache/ to save space after verification.")

if __name__ == "__main__":
    main()

# starry_core/main.py
import sys
import os
import platform
from datetime import datetime

__version__ = "0.1.0"

def print_banner():
    print("=" * 56)
    print("  Portable Starry")
    print("  Cross-Platform AI Agent")
    print(f"  Version: {__version__}")
    print("=" * 56)
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python:   {platform.python_version()}")
    print(f"  Time:     {datetime.now().isoformat()}")
    print("=" * 56)
    print()


def check_imports():
    """检查关键依赖是否可用"""
    print("[Core] Checking imports...")
    try:
        import fastapi
        print(f"  fastapi: {fastapi.__version__}")
    except ImportError as e:
        print(f"  fastapi: MISSING ({e})")
        return False

    try:
        import uvicorn
        print(f"  uvicorn: OK")
    except ImportError:
        print(f"  uvicorn: MISSING")
        return False

    try:
        import httpx
        print(f"  httpx: OK")
    except ImportError:
        print(f"  httpx: MISSING")
        return False

    try:
        import pydantic
        print(f"  pydantic: {pydantic.__version__}")
    except ImportError:
        print(f"  pydantic: MISSING")
        return False

    try:
        import psutil
        print(f"  psutil: {psutil.__version__}")
    except ImportError:
        print(f"  psutil: MISSING")

    print("[Core] All critical imports OK.")
    print()
    return True


def run_hardware_profiler():
    """运行硬件检测"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    profiler = os.path.join(base, "hardware_profiler.py")

    if not os.path.exists(profiler):
        print("[Hardware] Profiler not found, skipping.")
        print()
        return

    print("[Hardware] Running profiler...")
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, profiler],
            capture_output=True, text=True, timeout=30
        )
        # 只打印关键行
        for line in result.stdout.splitlines():
            if any(k in line for k in ["GPU", "CPU", "Memory", "Ollama", "NVIDIA", "✅", "❌", "Model:", "GPU 加速"]):
                print(f"  {line}")
        if result.returncode != 0:
            print(f"  [WARN] Profiler stderr: {result.stderr[:200]}")
    except Exception as e:
        print(f"  [WARN] Profiler failed: {e}")
    print()


def start_server():
    """启动 HTTP 服务"""
    print("[Server] Starting HTTP service...")

    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        import uvicorn

        app = FastAPI(
            title="Portable Starry",
            version=__version__,
            docs_url="/docs",
            redoc_url="/redoc"
        )

        @app.get("/", response_class=JSONResponse)
        def root():
            return {
                "status": "ok",
                "name": "Portable Starry",
                "version": __version__,
                "platform": f"{platform.system()} {platform.machine()}",
                "python": platform.python_version()
            }

        @app.get("/health")
        def health():
            return {"status": "running", "timestamp": datetime.now().isoformat()}

        print("  FastAPI ready at http://127.0.0.1:8080")
        print("  API docs: http://127.0.0.1:8080/docs")
        print()
        print("  Press Ctrl+C to stop the server.")
        print()
        uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")

    except ImportError as e:
        print(f"  [ERROR] Failed to start server: {e}")
        print("  Make sure fastapi and uvicorn are installed.")
        print()
        print("  Press Enter to exit...")
        input()


def main():
    print_banner()

    if not check_imports():
        print("[ERROR] Critical dependencies missing.")
        print("  Run: start.bat to install dependencies.")
        print()
        print("  Press Enter to exit...")
        input()
        return

    run_hardware_profiler()
    start_server()


if __name__ == "__main__":
    main()

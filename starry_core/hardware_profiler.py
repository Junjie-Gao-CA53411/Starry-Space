#!/usr/bin/env python3
"""
Portable Starry - Hardware Profiler (Production)
=================================================
跨平台硬件自动检测与 AI 推理配置推荐引擎
支持: Windows / macOS / Linux | x86_64 / ARM64
GPU: NVIDIA (CUDA) / AMD (ROCm/Vulkan) / Intel (Vulkan/OpenVINO) / Apple (Metal/MLX)

Version: 1.0.0
License: MIT
"""

from __future__ import annotations

import platform
import psutil
import subprocess
import json
import os
import re
import tempfile
import warnings
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from datetime import datetime


class ProfileEncoder(json.JSONEncoder):
    '''Custom JSON encoder supporting Enum serialization'''
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)

__version__ = "1.0.0"


class GPUVendor(Enum):
    NVIDIA = "NVIDIA"
    AMD = "AMD"
    INTEL = "Intel"
    APPLE = "Apple"
    UNKNOWN = "Unknown"


class OllamaBackend(Enum):
    CUDA = "cuda"
    ROCM = "rocm"
    VULKAN = "vulkan"
    METAL = "metal"
    MLX = "mlx"
    CPU = "cpu"


@dataclass
class GPUInfo:
    """GPU 信息"""
    name: str = "Unknown"
    vendor: GPUVendor = GPUVendor.UNKNOWN
    vram_mb: Optional[int] = None
    vram_gb: Optional[float] = None
    driver_version: Optional[str] = None
    pci_id: Optional[str] = None
    is_integrated: bool = False
    is_dedicated: bool = False
    is_display_adapter: bool = False
    compute_capability: Optional[str] = None
    backends: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.vram_mb and not self.vram_gb:
            self.vram_gb = round(self.vram_mb / 1024, 2)


@dataclass
class CPUInfo:
    """CPU 信息"""
    brand: str = "Unknown"
    physical_cores: int = 0
    logical_cores: int = 0
    frequency_mhz: Optional[float] = None
    architecture: str = ""
    flags: List[str] = field(default_factory=list)
    supports_avx2: bool = False
    supports_avx512: bool = False
    is_apple_silicon: bool = False


@dataclass
class MemoryInfo:
    """内存信息"""
    total_gb: float = 0.0
    available_gb: float = 0.0
    percent_used: float = 0.0
    swap_total_gb: float = 0.0
    swap_used_gb: float = 0.0
    type: Optional[str] = None


@dataclass
class DiskInfo:
    """磁盘信息"""
    device: str = ""
    mountpoint: str = ""
    filesystem: str = ""
    total_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    percent_used: float = 0.0
    is_ssd: bool = False


@dataclass
class OllamaConfig:
    """Ollama 推荐配置"""
    model_size: str = "7B"
    gpu_layers: int = 0
    use_gpu: bool = False
    context_length: int = 4096
    num_threads: int = 4
    backend: str = "cpu"
    quantization: str = "Q4_K_M"
    notes: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class SystemProfile:
    """完整系统画像"""
    version: str = __version__
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    os_name: str = ""
    os_version: str = ""
    os_release: str = ""
    hostname: str = ""
    architecture: str = ""
    cpu: CPUInfo = field(default_factory=CPUInfo)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    gpus: List[GPUInfo] = field(default_factory=list)
    disks: List[DiskInfo] = field(default_factory=list)
    battery: Optional[Dict[str, Any]] = None
    ai_backends: List[str] = field(default_factory=list)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, path: Optional[str] = None) -> str:
        data = self.to_dict()
        json_str = json.dumps(data, indent=2, ensure_ascii=False, cls=ProfileEncoder)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json_str)
        return json_str


class HardwareProfiler:
    """
    跨平台硬件检测器

    检测优先级（从高到低）：
    1. nvidia-smi (NVIDIA GPU，最可靠)
    2. NVML (nvidia-ml-py)
    3. dxdiag (Windows DirectX)
    4. PowerShell Get-CimInstance (Windows WMI)
    5. system_profiler (macOS)
    6. lspci (Linux)
    7. PnpDevice (Windows 备选)
    """

    def __init__(self, verbose: bool = False):
        self.system = platform.system()
        self.arch = platform.machine().lower()
        self.verbose = verbose
        self._detected_gpus: List[GPUInfo] = []

    def _log(self, msg: str):
        if self.verbose:
            print(f"[Profiler] {msg}")

    def _has_vendor(self, vendor: str) -> bool:
        return any(g.vendor.value == vendor for g in self._detected_gpus)

    # ═══════════════════════════════════════════════════════
    # CPU
    # ═══════════════════════════════════════════════════════
    def _get_cpu_info(self) -> CPUInfo:
        brand = platform.processor() or "Unknown"
        physical = psutil.cpu_count(logical=False) or 0
        logical = psutil.cpu_count(logical=True) or 0
        freq = psutil.cpu_freq()
        freq_mhz = freq.current if freq else None
        flags = []
        is_apple = False

        if self.system == "Darwin":
            brand = self._sysctl("machdep.cpu.brand_string") or brand
            physical = int(self._sysctl("hw.physicalcpu") or physical)
            logical = int(self._sysctl("hw.logicalcpu") or logical)
            freq_val = self._sysctl("hw.cpufrequency")
            if freq_val:
                freq_mhz = int(freq_val) / 1e6
            is_apple = "Apple" in brand

        elif self.system == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line and brand == "Unknown":
                            brand = line.split(":", 1)[1].strip()
                        if "flags" in line:
                            flags = line.split(":", 1)[1].strip().split()
            except:
                pass

        elif self.system == "Windows":
            brand, physical, logical, freq_mhz = self._get_cpu_windows()

        return CPUInfo(
            brand=brand,
            physical_cores=physical,
            logical_cores=logical,
            frequency_mhz=freq_mhz,
            architecture=self.arch,
            flags=flags,
            supports_avx2="avx2" in flags,
            supports_avx512="avx512f" in flags,
            is_apple_silicon=is_apple
        )

    def _get_cpu_windows(self) -> Tuple[str, int, int, Optional[float]]:
        brand = platform.processor() or "Unknown"
        physical = psutil.cpu_count(logical=False) or 0
        logical = psutil.cpu_count(logical=True) or 0
        freq_mhz = None

        try:
            ps_cmd = "Get-WmiObject Win32_Processor | Select-Object -First 1 | ForEach-Object { $_.Name + '|' + $_.NumberOfCores + '|' + $_.NumberOfLogicalProcessors + '|' + $_.MaxClockSpeed }"
            result = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and "|" in result.stdout:
                parts = result.stdout.strip().split("|")
                if len(parts) >= 4:
                    return parts[0].strip(), int(parts[1]), int(parts[2]), float(parts[3])
        except:
            pass

        return brand, physical, logical, freq_mhz

    # ═══════════════════════════════════════════════════════
    # Memory
    # ═══════════════════════════════════════════════════════
    def _get_memory_info(self) -> MemoryInfo:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        mem_type = None

        if self.system == "Darwin":
            mem_type = self._sysctl("hw.memtype")

        return MemoryInfo(
            total_gb=round(vm.total / (1024**3), 2),
            available_gb=round(vm.available / (1024**3), 2),
            percent_used=vm.percent,
            swap_total_gb=round(swap.total / (1024**3), 2),
            swap_used_gb=round(swap.used / (1024**3), 2),
            type=mem_type
        )

    # ═══════════════════════════════════════════════════════
    # GPU — 核心检测逻辑
    # ═══════════════════════════════════════════════════════
    def _get_gpu_info(self) -> List[GPUInfo]:
        gpus: List[GPUInfo] = []
        self._detected_gpus = []

        # 1. NVIDIA nvidia-smi (最可靠，绕过 Optimus)
        self._log("Trying nvidia-smi...")
        smi_gpus = self._detect_nvidia_smi()
        gpus.extend(smi_gpus)
        self._detected_gpus.extend(smi_gpus)

        # 2. NVIDIA NVML
        if not self._has_vendor("NVIDIA"):
            self._log("Trying NVML...")
            nvml_gpus = self._detect_nvidia_nvml()
            gpus.extend(nvml_gpus)
            self._detected_gpus.extend(nvml_gpus)

        # 3. Windows 多途径检测
        if self.system == "Windows":
            self._log("Trying dxdiag...")
            dx_gpus = self._detect_windows_dxdiag()
            merged_dx = self._merge_gpus(gpus, dx_gpus)
            gpus.extend(merged_dx)
            self._detected_gpus.extend(dx_gpus)

            self._log("Trying PowerShell WMI...")
            ps_gpus = self._detect_windows_powershell()
            merged_ps = self._merge_gpus(gpus, ps_gpus)
            gpus.extend(merged_ps)
            self._detected_gpus.extend(ps_gpus)

            self._log("Trying PnpDevice...")
            pnp_gpus = self._detect_windows_pnpdevice()
            merged_pnp = self._merge_gpus(gpus, pnp_gpus)
            gpus.extend(merged_pnp)
            self._detected_gpus.extend(pnp_gpus)

        # 4. macOS
        elif self.system == "Darwin":
            self._log("Trying system_profiler...")
            mac_gpus = self._detect_macos_gpu()
            gpus.extend(mac_gpus)
            self._detected_gpus.extend(mac_gpus)

        # 5. Linux
        elif self.system == "Linux":
            self._log("Trying lspci...")
            lspci_gpus = self._detect_linux_gpu()
            gpus.extend(lspci_gpus)
            self._detected_gpus.extend(lspci_gpus)

            self._log("Trying nvidia-smi (Linux)...")
            if not self._has_vendor("NVIDIA"):
                linux_smi = self._detect_nvidia_smi()
                gpus.extend(linux_smi)
                self._detected_gpus.extend(linux_smi)

        # 标记活动显示适配器
        self._mark_display_adapter(gpus)

        return gpus

    def _merge_gpus(self, existing: List[GPUInfo], new: List[GPUInfo]) -> List[GPUInfo]:
        """合并 GPU 列表，去重"""
        merged = []
        for g in new:
            if not any(self._gpu_matches(g, e) for e in existing):
                merged.append(g)
        return merged

    def _gpu_matches(self, a: GPUInfo, b: GPUInfo) -> bool:
        """判断两个 GPU 是否相同"""
        if a.name == b.name:
            return True
        if a.vendor == GPUVendor.NVIDIA and b.vendor == GPUVendor.NVIDIA:
            a_clean = re.sub(r'NVIDIA|GeForce|\s+', '', a.name.lower())
            b_clean = re.sub(r'NVIDIA|GeForce|\s+', '', b.name.lower())
            if a_clean in b_clean or b_clean in a_clean:
                return True
        return False

    def _mark_display_adapter(self, gpus: List[GPUInfo]):
        if self.system != "Windows" or not gpus:
            return
        try:
            result = subprocess.run(
                ["powershell", "-Command", 
                 "Get-CimInstance Win32_VideoController | Where-Object { $_.VideoModeDescription } | Select-Object -First 1 | ForEach-Object { $_.Name }"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                active_name = result.stdout.strip()
                for g in gpus:
                    if g.name == active_name or active_name in g.name or g.name in active_name:
                        g.is_display_adapter = True
        except:
            pass

    # ────────────────── 具体检测方法 ──────────────────

    def _detect_nvidia_smi(self) -> List[GPUInfo]:
        """nvidia-smi 命令行检测"""
        gpus = []
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        name = parts[0]
                        vram_str = parts[1]
                        driver = parts[2]
                        compute_cap = parts[3] if len(parts) > 3 else None

                        vram_mb = None
                        match = re.search(r'(\d+)', vram_str)
                        if match:
                            vram_mb = int(match.group(1))

                        gpus.append(GPUInfo(
                            name=name,
                            vendor=GPUVendor.NVIDIA,
                            vram_mb=vram_mb,
                            driver_version=driver,
                            compute_capability=compute_cap,
                            is_dedicated=True,
                            backends=["cuda", "vulkan"]
                        ))
        except FileNotFoundError:
            self._log("nvidia-smi not found")
        except Exception as e:
            self._log(f"nvidia-smi error: {e}")
        return gpus

    def _detect_nvidia_nvml(self) -> List[GPUInfo]:
        """NVML (nvidia-ml-py) 检测"""
        gpus = []
        try:
            from pynvml import (
                nvmlInit, nvmlShutdown, nvmlDeviceGetCount,
                nvmlDeviceGetHandleByIndex, nvmlDeviceGetName,
                nvmlDeviceGetMemoryInfo, nvmlDeviceGetDriverVersion
            )
            nvmlInit()
            for i in range(nvmlDeviceGetCount()):
                handle = nvmlDeviceGetHandleByIndex(i)
                name = nvmlDeviceGetName(handle)
                mem = nvmlDeviceGetMemoryInfo(handle)
                gpus.append(GPUInfo(
                    name=name,
                    vendor=GPUVendor.NVIDIA,
                    vram_mb=round(mem.total / (1024**2)),
                    driver_version=nvmlDeviceGetDriverVersion(handle),
                    is_dedicated=True,
                    backends=["cuda", "vulkan"]
                ))
            nvmlShutdown()
        except ImportError:
            self._log("nvidia-ml-py not installed")
        except Exception as e:
            self._log(f"NVML error: {e}")
        return gpus

    def _detect_windows_dxdiag(self) -> List[GPUInfo]:
        """dxdiag XML 导出检测"""
        gpus = []
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
                tmp_path = tmp.name

            subprocess.run(["dxdiag", "/x", tmp_path], capture_output=True, timeout=30)

            if os.path.exists(tmp_path):
                import xml.etree.ElementTree as ET
                tree = ET.parse(tmp_path)
                root = tree.getroot()

                for display in root.findall(".//DisplayDevice"):
                    name = display.findtext("cardName", "")
                    if not name or self._is_basic_display(name):
                        continue

                    vram_str = (display.findtext("displayMemory", "") or 
                               display.findtext("dedicatedMemory", ""))
                    vendor = self._detect_vendor(name)
                    vram_mb = self._parse_dxdiag_vram(vram_str)
                    is_integrated = self._is_integrated(name)

                    gpus.append(GPUInfo(
                        name=name,
                        vendor=vendor,
                        vram_mb=vram_mb,
                        is_integrated=is_integrated,
                        is_dedicated=not is_integrated,
                        backends=self._infer_backends(vendor, name)
                    ))
        except Exception as e:
            self._log(f"dxdiag error: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
        return gpus

    def _detect_windows_powershell(self) -> List[GPUInfo]:
        """PowerShell Get-CimInstance 检测"""
        gpus = []
        try:
            ps_cmd = """
            $gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notlike "*Microsoft Basic*" };
            foreach ($g in $gpus) {
                $vram = 0;
                if ($g.AdapterRAM -and $g.AdapterRAM -gt 0) {
                    try { $vram = [math]::Round($g.AdapterRAM / 1MB) } catch {}
                }
                Write-Output ($g.Name + "|" + $vram + "|" + $g.DriverVersion + "|" + $g.PNPDeviceID)
            }
            """
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line or "|" not in line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        if self._is_basic_display(name):
                            continue
                        vram = int(parts[1]) if parts[1].isdigit() and int(parts[1]) > 0 else None
                        driver = parts[2].strip() if len(parts) > 2 else None
                        vendor = self._detect_vendor(name)
                        is_integrated = self._is_integrated(name)

                        gpus.append(GPUInfo(
                            name=name,
                            vendor=vendor,
                            vram_mb=vram,
                            driver_version=driver,
                            is_integrated=is_integrated,
                            is_dedicated=not is_integrated,
                            backends=self._infer_backends(vendor, name)
                        ))
        except Exception as e:
            self._log(f"PowerShell error: {e}")
        return gpus

    def _detect_windows_pnpdevice(self) -> List[GPUInfo]:
        """PnpDevice 检测（能看到被禁用的设备）"""
        gpus = []
        try:
            ps_cmd = """
            Get-PnpDevice -Class Display | Where-Object { $_.Name -notlike "*Microsoft Basic*" } | ForEach-Object { 
                Write-Output ($_.Name + "|" + $_.Status + "|" + $_.InstanceId) 
            }
            """
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line or "|" not in line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        if self._is_basic_display(name):
                            continue
                        vendor = self._detect_vendor(name)
                        is_integrated = self._is_integrated(name)

                        if not any(name in g.name or g.name in name for g in gpus):
                            gpus.append(GPUInfo(
                                name=name,
                                vendor=vendor,
                                is_integrated=is_integrated,
                                is_dedicated=not is_integrated,
                                backends=self._infer_backends(vendor, name)
                            ))
        except Exception as e:
            self._log(f"PnpDevice error: {e}")
        return gpus

    def _detect_macos_gpu(self) -> List[GPUInfo]:
        gpus = []
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for d in data.get("SPDisplaysDataType", []):
                    name = d.get("sppci_model", "Unknown")
                    vendor = GPUVendor.APPLE if "Apple" in name else GPUVendor.UNKNOWN
                    vram = d.get("sppci_vram")
                    vram_mb = None if vram == "Shared with system" else self._parse_vram(vram)
                    backends = ["mps", "metal", "mlx"] if "Apple" in name else []
                    gpus.append(GPUInfo(
                        name=name,
                        vendor=vendor,
                        vram_mb=vram_mb,
                        is_integrated="Apple" in name or "Intel" in name,
                        backends=backends
                    ))
        except Exception as e:
            self._log(f"macOS error: {e}")
        return gpus

    def _detect_linux_gpu(self) -> List[GPUInfo]:
        gpus = []
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10)
            for line in result.stdout.split("\n"):
                if any(k in line for k in ["VGA", "3D", "Display"]):
                    name = line.split(":")[-1].strip()
                    vendor = self._detect_vendor(name)
                    gpus.append(GPUInfo(
                        name=name,
                        vendor=vendor,
                        backends=self._infer_backends(vendor, name)
                    ))
        except Exception as e:
            self._log(f"Linux error: {e}")
        return gpus

    # ═══════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════
    def _is_basic_display(self, name: str) -> bool:
        return any(k in name.lower() for k in ["microsoft basic", "basic display", "basic render"])

    def _is_integrated(self, name: str) -> bool:
        n = name.lower()
        return any(k in n for k in ["intel", "arc", "iris", "uhd", "hd graphics", "radeon graphics", "vega"])

    def _detect_vendor(self, name: str) -> GPUVendor:
        n = name.lower()
        if any(k in n for k in ["nvidia", "geforce", "rtx", "quadro", "tesla", "a100", "h100"]):
            return GPUVendor.NVIDIA
        if any(k in n for k in ["amd", "radeon", "rx ", "firepro", "instinct"]):
            return GPUVendor.AMD
        if any(k in n for k in ["intel", "arc", "iris", "uhd", "hd graphics", "xe"]):
            return GPUVendor.INTEL
        if "apple" in n:
            return GPUVendor.APPLE
        return GPUVendor.UNKNOWN

    def _infer_backends(self, vendor: GPUVendor, name: str) -> List[str]:
        n = name.lower()
        backends = []

        if vendor == GPUVendor.NVIDIA:
            backends = ["cuda"]
            if any(k in n for k in ["rtx", "gtx 16", "quadro", "tesla"]):
                backends.append("vulkan")
            if any(k in n for k in ["a100", "h100", "a6000"]):
                backends.append("cuda-v12")

        elif vendor == GPUVendor.AMD:
            backends = ["vulkan"]
            if self.system == "Linux":
                backends.append("rocm")
            if "instinct" in n or "mi" in n:
                backends.append("rocm-datacenter")

        elif vendor == GPUVendor.INTEL:
            backends = ["vulkan", "openvino"]
            if "arc" in n:
                backends.append("intel-xpu")

        elif vendor == GPUVendor.APPLE:
            backends = ["mps", "metal", "mlx"]

        return backends

    def _parse_vram(self, vram_str) -> Optional[int]:
        if vram_str is None:
            return None
        s = str(vram_str).lower().replace(",", "").replace(" ", "")
        try:
            if "gb" in s:
                return int(float(s.replace("gb", "")) * 1024)
            elif "mb" in s:
                return int(float(s.replace("mb", "")))
            elif "kb" in s:
                return int(float(s.replace("kb", "")) / 1024)
            else:
                val = int(s)
                if val > 1e9:
                    return int(val / (1024**2))
                elif val > 1e6:
                    return int(val / 1024)
                return val
        except:
            return None

    def _parse_dxdiag_vram(self, vram_str: str) -> Optional[int]:
        if not vram_str:
            return None
        match = re.search(r'(\d+)\s*MB', vram_str, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r'(\d+)', vram_str)
        if match:
            val = int(match.group(1))
            if val > 1000:
                return val
            if val > 1:
                return val * 1024
        return None

    def _sysctl(self, key: str) -> Optional[str]:
        try:
            return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        except:
            return None

    # ═══════════════════════════════════════════════════════
    # Disk
    # ═══════════════════════════════════════════════════════
    def _get_disk_info(self) -> List[DiskInfo]:
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                is_ssd = False
                if self.system == "Windows":
                    try:
                        result = subprocess.run(
                            ["powershell", "-Command", 
                             f"Get-PhysicalDisk | Where-Object {{ $_.DeviceId -eq (Get-Partition -DriveLetter '{part.mountpoint[0]}').DiskNumber }} | Select-Object MediaType"],
                            capture_output=True, text=True, timeout=5
                        )
                        is_ssd = "SSD" in result.stdout
                    except:
                        pass

                disks.append(DiskInfo(
                    device=part.device,
                    mountpoint=part.mountpoint,
                    filesystem=part.fstype,
                    total_gb=round(usage.total / (1024**3), 2),
                    used_gb=round(usage.used / (1024**3), 2),
                    free_gb=round(usage.free / (1024**3), 2),
                    percent_used=usage.percent,
                    is_ssd=is_ssd
                ))
            except PermissionError:
                continue
        return disks

    # ═══════════════════════════════════════════════════════
    # Battery
    # ═══════════════════════════════════════════════════════
    def _get_battery_info(self) -> Optional[Dict[str, Any]]:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": battery.percent,
                "is_plugged": battery.power_plugged,
                "secs_left": battery.secsleft if battery.secsleft != -1 else None
            }
        return None

    # ═══════════════════════════════════════════════════════
    # AI Backends
    # ═══════════════════════════════════════════════════════
    def _detect_ai_backends(self, gpus: List[GPUInfo]) -> List[str]:
        backends = ["cpu"]

        try:
            import torch
            if torch.cuda.is_available():
                backends.append("pytorch-cuda")
                for i in range(torch.cuda.device_count()):
                    backends.append(f"cuda:{torch.cuda.get_device_name(i)}")
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                backends.append("pytorch-mps")
        except ImportError:
            pass

        try:
            import tensorflow as tf
            if len(tf.config.list_physical_devices('GPU')) > 0:
                backends.append("tensorflow-gpu")
        except ImportError:
            pass

        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" in providers:
                backends.append("onnx-cuda")
            if "DmlExecutionProvider" in providers:
                backends.append("onnx-directml")
        except ImportError:
            pass

        for gpu in gpus:
            for b in gpu.backends:
                if b not in backends:
                    backends.append(b)

        return backends

    # ═══════════════════════════════════════════════════════
    # Ollama Config Recommendation
    # ═══════════════════════════════════════════════════════
    def _get_ollama_config(self, profile: SystemProfile) -> OllamaConfig:
        config = OllamaConfig(
            model_size="7B",
            gpu_layers=0,
            use_gpu=False,
            context_length=4096,
            num_threads=max(1, profile.cpu.logical_cores - 2),
            backend="cpu",
            quantization="Q4_K_M",
            notes=[],
            env_vars={}
        )

        nvidia_gpus = [g for g in profile.gpus if g.vendor == GPUVendor.NVIDIA and g.is_dedicated]
        apple_gpus = [g for g in profile.gpus if g.vendor == GPUVendor.APPLE]
        intel_gpus = [g for g in profile.gpus if g.vendor == GPUVendor.INTEL]
        amd_gpus = [g for g in profile.gpus if g.vendor == GPUVendor.AMD]

        total_nvidia_vram = sum(g.vram_mb or 0 for g in nvidia_gpus)

        # NVIDIA
        if nvidia_gpus and total_nvidia_vram > 0:
            config.use_gpu = True
            config.backend = "cuda"
            config.env_vars["OLLAMA_GPU_OVERHEAD"] = "1"

            gpu = nvidia_gpus[0]
            config.notes.append(f"NVIDIA: {gpu.name} ({gpu.vram_gb}GB)")

            if gpu.compute_capability:
                config.notes.append(f"Compute Capability: {gpu.compute_capability}")
                if gpu.compute_capability in ["8.0", "8.6", "8.9", "9.0", "12.0"]:
                    config.notes.append("Ampere/Ada/Blackwell architecture - optimal performance")
                elif gpu.compute_capability in ["7.0", "7.5"]:
                    config.notes.append("Turing - good performance")

            if total_nvidia_vram >= 80000:
                config.model_size = "70B"
                config.gpu_layers = 999
                config.context_length = 131072
            elif total_nvidia_vram >= 40000:
                config.model_size = "70B"
                config.gpu_layers = 999
                config.context_length = 65536
            elif total_nvidia_vram >= 24000:
                config.model_size = "70B"
                config.gpu_layers = 999
                config.context_length = 32768
            elif total_nvidia_vram >= 16000:
                config.model_size = "32B"
                config.gpu_layers = 999
                config.context_length = 16384
            elif total_nvidia_vram >= 8000:
                config.model_size = "14B"
                config.gpu_layers = 999
                config.context_length = 8192
            elif total_nvidia_vram >= 6000:
                config.model_size = "7B"
                config.gpu_layers = 999
                config.context_length = 8192
            elif total_nvidia_vram >= 4000:
                config.model_size = "7B"
                config.gpu_layers = 999
                config.context_length = 4096
            else:
                config.model_size = "3B"
                config.gpu_layers = 20
                config.notes.append("Low VRAM - partial GPU offload recommended")

        # Apple Silicon
        elif apple_gpus:
            config.use_gpu = True
            config.backend = "metal"
            config.env_vars["OLLAMA_METAL"] = "1"
            config.notes.append(f"Apple Silicon: {profile.memory.total_gb}GB unified memory")

            if profile.memory.total_gb >= 64:
                config.model_size = "70B"
                config.context_length = 32768
            elif profile.memory.total_gb >= 32:
                config.model_size = "32B"
                config.context_length = 16384
            elif profile.memory.total_gb >= 16:
                config.model_size = "14B"
                config.context_length = 8192
            else:
                config.model_size = "7B"
                config.context_length = 4096

        # Intel
        elif intel_gpus:
            config.notes.append(f"Intel GPU: {intel_gpus[0].name}")
            config.notes.append("Ollama v0.30.11+ supports Intel Vulkan backend")
            config.notes.append("Set OLLAMA_GPU=vulkan to enable")

            if nvidia_gpus:
                config.notes.append("NVIDIA + Intel detected, prefer NVIDIA")
            else:
                config.backend = "vulkan"
                config.use_gpu = True
                config.gpu_layers = 999
                config.env_vars["OLLAMA_GPU"] = "vulkan"

            if profile.memory.total_gb >= 32:
                config.model_size = "14B"
            elif profile.memory.total_gb >= 16:
                config.model_size = "7B"
            else:
                config.model_size = "3B"

        # AMD
        elif amd_gpus:
            config.notes.append(f"AMD GPU: {amd_gpus[0].name}")
            if self.system == "Linux":
                config.backend = "rocm"
                config.use_gpu = True
                config.gpu_layers = 999
                config.env_vars["OLLAMA_GPU"] = "rocm"
                config.notes.append("Linux: ROCm backend available")
            else:
                config.backend = "vulkan"
                config.use_gpu = True
                config.gpu_layers = 999
                config.env_vars["OLLAMA_GPU"] = "vulkan"
                config.notes.append("Windows: Vulkan backend")

        # CPU Only
        else:
            config.notes.append("CPU-only inference mode")
            config.env_vars["OLLAMA_CPU_ONLY"] = "1"

            if profile.cpu.supports_avx512:
                config.notes.append("AVX-512 supported - best CPU performance")
            elif profile.cpu.supports_avx2:
                config.notes.append("AVX2 supported - good CPU performance")
            else:
                config.notes.append("No AVX2/AVX-512 - CPU performance limited")

            if profile.memory.total_gb >= 64:
                config.model_size = "32B"
            elif profile.memory.total_gb >= 32:
                config.model_size = "14B"
            elif profile.memory.total_gb >= 16:
                config.model_size = "7B"
            else:
                config.model_size = "3B"
                config.quantization = "Q4_0"
                config.notes.append("Low memory - using Q4_0 quantization")

        # Memory correction
        if profile.memory.total_gb < 8 and config.model_size in ("14B", "32B", "70B"):
            config.model_size = "7B"
            config.notes.append("Memory insufficient - downgrading model")

        # Multi-GPU
        if len(profile.gpus) > 1:
            config.notes.append(f"Multi-GPU Setup ({len(profile.gpus)} GPUs):")
            for g in profile.gpus:
                adapter_mark = " [Display]" if g.is_display_adapter else ""
                config.notes.append(f"  - {g.name} ({g.vendor.value}){adapter_mark}")

        # Environment variables
        config.env_vars["OLLAMA_NUM_THREADS"] = str(config.num_threads)
        if config.context_length > 4096:
            config.env_vars["OLLAMA_CONTEXT_LENGTH"] = str(config.context_length)

        return config

    # ═══════════════════════════════════════════════════════
    # Main
    # ═══════════════════════════════════════════════════════
    def profile(self) -> SystemProfile:
        cpu = self._get_cpu_info()
        memory = self._get_memory_info()
        gpus = self._get_gpu_info()
        disks = self._get_disk_info()
        battery = self._get_battery_info()
        ai_backends = self._detect_ai_backends(gpus)

        profile = SystemProfile(
            timestamp=datetime.now().isoformat(),
            os_name=self.system,
            os_version=platform.version(),
            os_release=platform.release(),
            hostname=platform.node(),
            architecture=self.arch,
            cpu=cpu,
            memory=memory,
            gpus=gpus,
            disks=disks,
            battery=battery,
            ai_backends=ai_backends,
        )

        profile.ollama = self._get_ollama_config(profile)
        return profile


# ═══════════════════════════════════════════════════════
# CLI Output
# ═══════════════════════════════════════════════════════

def print_profile(p: SystemProfile):
    print("=" * 56)
    print("  Portable Starry - Hardware Profiler v1.0.0")
    print("=" * 56)

    print(f"\nSystem: {p.os_name} {p.os_release} ({p.architecture})")
    print(f"Host: {p.hostname}")

    print(f"\nCPU: {p.cpu.brand}")
    print(f"  Cores: {p.cpu.physical_cores}P / {p.cpu.logical_cores}L")
    if p.cpu.frequency_mhz:
        print(f"  Frequency: {p.cpu.frequency_mhz:.0f} MHz")
    if p.cpu.supports_avx512:
        print(f"  SIMD: AVX-512")
    elif p.cpu.supports_avx2:
        print(f"  SIMD: AVX2")

    print(f"\nMemory: {p.memory.total_gb}GB total / {p.memory.available_gb}GB available")

    print(f"\nGPUs ({len(p.gpus)} detected):")
    if not p.gpus:
        print("  No GPU detected")
    for i, g in enumerate(p.gpus, 1):
        vram = f"{g.vram_gb}GB" if g.vram_gb else "Shared"
        gpu_type = "dGPU" if g.is_dedicated else "iGPU" if g.is_integrated else "?"
        display = " [Display]" if g.is_display_adapter else ""
        backends = ", ".join(g.backends) if g.backends else "None"
        print(f"  [{i}] {gpu_type} {g.name}{display}")
        print(f"      Vendor: {g.vendor.value} | VRAM: {vram}")
        if g.driver_version:
            print(f"      Driver: {g.driver_version}")
        if g.compute_capability:
            print(f"      Compute: {g.compute_capability}")
        print(f"      Backends: {backends}")

    print(f"\nDisks:")
    for d in p.disks:
        ssd_mark = " [SSD]" if d.is_ssd else ""
        print(f"  {d.device} -> {d.total_gb}GB total, {d.free_gb}GB free ({d.percent_used}% used){ssd_mark}")

    if p.battery:
        print(f"\nBattery: {p.battery['percent']}% {'(Charging)' if p.battery['is_plugged'] else ''}")

    print(f"\nAI Backends: {', '.join(p.ai_backends)}")

    print(f"\nOllama Recommendation:")
    cfg = p.ollama
    print(f"  Model: {cfg.model_size} ({cfg.quantization})")
    print(f"  GPU: {'Yes' if cfg.use_gpu else 'No'} ({cfg.backend})")
    print(f"  Context: {cfg.context_length}")
    print(f"  Threads: {cfg.num_threads}")
    print(f"  GPU Layers: {cfg.gpu_layers}")

    if cfg.env_vars:
        print(f"\n  Environment Variables:")
        for k, v in cfg.env_vars.items():
            print(f"    {k}={v}")

    for note in cfg.notes:
        print(f"  * {note}")

    print("\n" + "=" * 56)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Portable Starry Hardware Profiler")
    parser.add_argument("-o", "--output", default="hardware_profile.json", help="Output JSON file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--env", action="store_true", help="Print environment variables only")
    args = parser.parse_args()

    profiler = HardwareProfiler(verbose=args.verbose)
    profile = profiler.profile()

    if args.env:
        for k, v in profile.ollama.env_vars.items():
            print(f"{k}={v}")
    else:
        print_profile(profile)
        profile.to_json(args.output)
        print(f"\nSaved to: {args.output}")


if __name__ == "__main__":
    main()

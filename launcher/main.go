package main

import (
	"crypto/sha256"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const (
	corePort     = "8000"
	webuiPort    = "8080"
	profilePath  = "config/hardware-profile.json"
	sitePkgDir   = "runtime/site-packages"
	requirements = "runtime/requirements.txt"
)

// ==================== 数据结构 ====================

type PlatformInfo struct {
	OS   string `json:"os"`
	Arch string `json:"arch"`
}

type CPUInfo struct {
	Model        string  `json:"model"`
	Cores        int     `json:"cores"`
	Threads      int     `json:"threads"`
	FrequencyMHz int     `json:"frequency_mhz"`
}

type MemoryInfo struct {
	TotalGB     float64 `json:"total_gb"`
	AvailableGB float64 `json:"available_gb"`
}

type GPUInfo struct {
	Name   string  `json:"name"`
	VRAMGB float64 `json:"vram_gb"`
}

type StorageInfo struct {
	TotalGB     float64 `json:"total_gb"`
	AvailableGB float64 `json:"available_gb"`
}

type DeviceProfile struct {
	ID              string       `json:"id"`
	Hostname        string       `json:"hostname"`
	FirstSeen       string       `json:"first_seen"`
	LastSeen        string       `json:"last_seen"`
	Platform        PlatformInfo `json:"platform"`
	CPU             CPUInfo      `json:"cpu"`
	Memory          MemoryInfo   `json:"memory"`
	GPUs            []GPUInfo    `json:"gpu"`
	Storage         StorageInfo  `json:"storage"`
	RecommendedTier string       `json:"recommended_tier"`
}

type HardwareProfile struct {
	Version  string          `json:"version"`
	Profiles []DeviceProfile `json:"profiles"`
}

// ==================== 主入口 ====================

func main() {
	rootDir, err := getRootDir()
	if err != nil {
		fatal("无法获取根目录: %v", err)
	}

	// 1. 检测平台
	plat := detectPlatform()
	fmt.Printf("[Starry] 检测到平台: %s/%s\n", plat.OS, plat.Arch)

	// 2. 检测硬件
	profile := detectHardware(plat)
	fmt.Printf("[Starry] 设备指纹: %s | 推荐层级: %s\n", profile.ID, profile.RecommendedTier)

	// 3. 更新硬件档案
	if err := updateHardwareProfile(rootDir, profile); err != nil {
		fmt.Fprintf(os.Stderr, "[Warning] 更新硬件档案失败: %v\n", err)
	}

	// 4. 定位运行时
	uvPath, pythonPath, err := getRuntimePaths(rootDir, plat)
	if err != nil {
		fatal("运行时定位失败: %v", err)
	}
	fmt.Printf("[Starry] UV: %s\n", uvPath)
	fmt.Printf("[Starry] Python: %s\n", pythonPath)

	// 确保可执行权限（Linux/macOS）
	_ = ensureExecutable(uvPath)
	_ = ensureExecutable(pythonPath)

	// 5. 安装依赖（无venv，用 --target + PYTHONPATH）
	if err := ensureDependencies(rootDir, uvPath, pythonPath); err != nil {
		fatal("依赖安装失败: %v", err)
	}

	// 6. 构建环境变量
	env := buildEnv(rootDir, profile.RecommendedTier)

	// 7. 启动 starry-core
	coreCmd, err := startProcess(pythonPath, []string{filepath.Join(rootDir, "starry-core", "main.py")}, env, rootDir)
	if err != nil {
		fatal("启动 starry-core 失败: %v", err)
	}
	fmt.Println("[Starry] starry-core 已启动")

	// 8. 启动 webui（如果存在）
	var webuiCmd *exec.Cmd
	webuiEntries := []string{
		filepath.Join(rootDir, "webui", "main.py"),
		filepath.Join(rootDir, "webui", "server.py"),
		filepath.Join(rootDir, "webui", "app.py"),
	}
	for _, entry := range webuiEntries {
		if _, err := os.Stat(entry); err == nil {
			webuiCmd, err = startProcess(pythonPath, []string{entry}, env, filepath.Dir(entry))
			if err != nil {
				fmt.Fprintf(os.Stderr, "[Warning] 启动 webui 失败: %v\n", err)
			} else {
				fmt.Printf("[Starry] webui 已启动: %s\n", entry)
			}
			break
		}
	}
	if webuiCmd == nil {
		fmt.Println("[Starry] 未找到独立 webui，假设 core 自带 Web 服务")
	}

	// 9. 等待服务就绪
	fmt.Println("[Starry] 等待服务启动...")
	time.Sleep(2 * time.Second)

	// 10. 打开浏览器
	url := "http://localhost:" + webuiPort
	if err := openBrowser(url); err != nil {
		fmt.Printf("[Starry] 请手动打开浏览器访问: %s\n", url)
	}

	fmt.Println("[Starry] Starry Space 运行中，按 Ctrl+C 停止")

	// 11. 信号处理
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	<-sigCh

	fmt.Println("\n[Starry] 正在关闭服务...")
	killProcess(coreCmd)
	killProcess(webuiCmd)
	fmt.Println("[Starry] 已退出")
}

// ==================== 目录与路径 ====================

func getRootDir() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	return filepath.Dir(exe), nil
}

func detectPlatform() PlatformInfo {
	arch := runtime.GOARCH
	if arch == "amd64" {
		arch = "x86_64"
	} else if arch == "arm64" {
		arch = "aarch64"
	}

	osName := runtime.GOOS
	if osName == "darwin" {
		osName = "macos"
	}

	return PlatformInfo{OS: osName, Arch: arch}
}

func getRuntimePaths(rootDir string, plat PlatformInfo) (uvPath, pythonPath string, err error) {
	// UV 路径
	uvName := fmt.Sprintf("uv-%s-%s", plat.OS, plat.Arch)
	if plat.OS == "windows" {
		uvName += ".exe"
	}
	uvPath = filepath.Join(rootDir, "runtime", uvName)

	// Python 路径
	var pyDirName string
	switch plat.OS {
	case "windows":
		pyDirName = fmt.Sprintf("cpython-3.13.14-windows-%s-none", plat.Arch)
		pythonPath = filepath.Join(rootDir, "runtime", "bootstrap", pyDirName, "python.exe")
	case "linux":
		pyDirName = fmt.Sprintf("cpython-3.13.14-linux-%s-gnu", plat.Arch)
		pythonPath = filepath.Join(rootDir, "runtime", "bootstrap", pyDirName, "bin", "python")
	case "macos":
		pyDirName = fmt.Sprintf("cpython-3.13.14-macos-%s-none", plat.Arch)
		pythonPath = filepath.Join(rootDir, "runtime", "bootstrap", pyDirName, "bin", "python")
	}

	// 验证存在
	if _, err := os.Stat(uvPath); err != nil {
		return "", "", fmt.Errorf("UV 未找到: %s", uvPath)
	}
	if _, err := os.Stat(pythonPath); err != nil {
		return "", "", fmt.Errorf("Python 未找到: %s", pythonPath)
	}
	return uvPath, pythonPath, nil
}

func ensureExecutable(path string) error {
	if runtime.GOOS == "windows" {
		return nil
	}
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	if info.Mode()&0111 == 0 {
		return os.Chmod(path, info.Mode()|0755)
	}
	return nil
}

// ==================== 依赖管理（无 venv） ====================

func ensureDependencies(rootDir, uvPath, pythonPath string) error {
	targetDir := filepath.Join(rootDir, sitePkgDir)
	reqFile := filepath.Join(rootDir, requirements)
	markerFile := filepath.Join(targetDir, ".starry-installed")

	// 检查 requirements.txt 是否存在
	reqStat, err := os.Stat(reqFile)
	if err != nil {
		return fmt.Errorf("requirements.txt 不存在: %w", err)
	}

	// 检查是否已安装且未过期
	if markerStat, err := os.Stat(markerFile); err == nil {
		if markerStat.ModTime().After(reqStat.ModTime()) {
			fmt.Println("[Starry] 依赖已是最新，跳过安装")
			return nil
		}
	}

	fmt.Println("[Starry] 正在安装依赖...")
	_ = os.MkdirAll(targetDir, 0755)

	cmd := exec.Command(uvPath, "pip", "install",
		"--python", pythonPath,
		"--target", targetDir,
		"--no-cache",
		"-r", reqFile,
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Dir = rootDir

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("uv pip install 失败: %w", err)
	}

	// 写入标记文件
	f, err := os.Create(markerFile)
	if err != nil {
		return err
	}
	f.Close()
	fmt.Println("[Starry] 依赖安装完成")
	return nil
}

func buildEnv(rootDir, tier string) []string {
	env := os.Environ()
	sitePkg := filepath.Join(rootDir, sitePkgDir)

	// 设置 PYTHONPATH（追加或新建）
	found := false
	sep := string(os.PathListSeparator)
	for i, e := range env {
		if strings.HasPrefix(e, "PYTHONPATH=") {
			env[i] = e + sep + sitePkg
			found = true
			break
		}
	}
	if !found {
		env = append(env, "PYTHONPATH="+sitePkg)
	}

	env = append(env, "STARRY_ROOT="+rootDir)
	env = append(env, "STARRY_TIER="+tier)
	env = append(env, "STARRY_CORE_PORT="+corePort)
	env = append(env, "STARRY_WEBUI_PORT="+webuiPort)
	return env
}

// ==================== 硬件检测 ====================

func detectHardware(plat PlatformInfo) DeviceProfile {
	hostname, _ := os.Hostname()
	cpu := detectCPU(plat)
	mem := detectMemory(plat)
	gpus := detectGPUs(plat)
	storage := detectStorage()

	tier := recommendTier(mem, gpus)

	// 生成设备指纹
	fp := fmt.Sprintf("%s|%s|%d|%s", hostname, cpu.Model, int(mem.TotalGB), gpuFingerprint(gpus))
	id := fmt.Sprintf("%x", sha256.Sum256([]byte(fp)))[:16]
	now := time.Now().Format(time.RFC3339)

	return DeviceProfile{
		ID:              id,
		Hostname:        hostname,
		FirstSeen:       now,
		LastSeen:        now,
		Platform:        plat,
		CPU:             cpu,
		Memory:          mem,
		GPUs:            gpus,
		Storage:         storage,
		RecommendedTier: tier,
	}
}

func detectCPU(plat PlatformInfo) CPUInfo {
	cpu := CPUInfo{Model: "Unknown", Cores: 0, Threads: 0, FrequencyMHz: 0}

	switch plat.OS {
	case "windows":
		// wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed /format:csv
		out, err := exec.Command("wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed", "/format:csv").Output()
		if err == nil {
			lines := strings.Split(string(out), "\n")
			for _, line := range lines {
				line = strings.TrimSpace(line)
				if line == "" || strings.HasPrefix(line, "Node") {
					continue
				}
				parts := strings.Split(line, ",")
				if len(parts) >= 5 {
					cpu.Model = strings.TrimSpace(parts[1])
					cpu.Cores, _ = strconv.Atoi(strings.TrimSpace(parts[2]))
					cpu.Threads, _ = strconv.Atoi(strings.TrimSpace(parts[3]))
					cpu.FrequencyMHz, _ = strconv.Atoi(strings.TrimSpace(parts[4]))
					break
				}
			}
		}

	case "linux":
		// 读取 /proc/cpuinfo
		data, err := os.ReadFile("/proc/cpuinfo")
		if err == nil {
			lines := strings.Split(string(data), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "model name") {
					cpu.Model = strings.TrimSpace(strings.SplitN(line, ":", 2)[1])
				} else if strings.HasPrefix(line, "cpu cores") {
					cpu.Cores, _ = strconv.Atoi(strings.TrimSpace(strings.SplitN(line, ":", 2)[1]))
				} else if strings.HasPrefix(line, "siblings") {
					cpu.Threads, _ = strconv.Atoi(strings.TrimSpace(strings.SplitN(line, ":", 2)[1]))
				} else if strings.HasPrefix(line, "cpu MHz") {
					mhz, _ := strconv.ParseFloat(strings.TrimSpace(strings.SplitN(line, ":", 2)[1]), 64)
					cpu.FrequencyMHz = int(mhz)
				}
			}
		}

	case "macos":
		model, _ := exec.Command("sysctl", "-n", "machdep.cpu.brand_string").Output()
		cores, _ := exec.Command("sysctl", "-n", "hw.physicalcpu").Output()
		threads, _ := exec.Command("sysctl", "-n", "hw.logicalcpu").Output()
		freq, _ := exec.Command("sysctl", "-n", "hw.cpufrequency_max").Output()

		cpu.Model = strings.TrimSpace(string(model))
		cpu.Cores, _ = strconv.Atoi(strings.TrimSpace(string(cores)))
		cpu.Threads, _ = strconv.Atoi(strings.TrimSpace(string(threads)))
		if f, err := strconv.ParseInt(strings.TrimSpace(string(freq)), 10, 64); err == nil {
			cpu.FrequencyMHz = int(f / 1_000_000) // Hz to MHz
		}
	}

	return cpu
}

func detectMemory(plat PlatformInfo) MemoryInfo {
	mem := MemoryInfo{}

	switch plat.OS {
	case "windows":
		out, err := exec.Command("wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/format:csv").Output()
		if err == nil {
			lines := strings.Split(string(out), "\n")
			for _, line := range lines {
				line = strings.TrimSpace(line)
				if line == "" || strings.HasPrefix(line, "Node") {
					continue
				}
				parts := strings.Split(line, ",")
				if len(parts) >= 2 {
					bytes, _ := strconv.ParseInt(strings.TrimSpace(parts[1]), 10, 64)
					mem.TotalGB = float64(bytes) / (1024 * 1024 * 1024)
					break
				}
			}
		}

	case "linux":
		data, err := os.ReadFile("/proc/meminfo")
		if err == nil {
			lines := strings.Split(string(data), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "MemTotal:") {
					fields := strings.Fields(line)
					if len(fields) >= 2 {
						kb, _ := strconv.ParseInt(fields[1], 10, 64)
						mem.TotalGB = float64(kb) / (1024 * 1024)
					}
					break
				}
			}
		}

	case "macos":
		out, err := exec.Command("sysctl", "-n", "hw.memsize").Output()
		if err == nil {
			bytes, _ := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
			mem.TotalGB = float64(bytes) / (1024 * 1024 * 1024)
		}
	}

	// Available 简化处理，不实时检测
	mem.AvailableGB = mem.TotalGB * 0.6
	return mem
}

func detectGPUs(plat PlatformInfo) []GPUInfo {
	var gpus []GPUInfo

	switch plat.OS {
	case "windows":
		// wmic path win32_VideoController get Name,AdapterRAM /format:csv
		out, err := exec.Command("wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv").Output()
		if err == nil {
			lines := strings.Split(string(out), "\n")
			for _, line := range lines {
				line = strings.TrimSpace(line)
				if line == "" || strings.HasPrefix(line, "Node") {
					continue
				}
				parts := strings.Split(line, ",")
				if len(parts) >= 3 {
					name := strings.TrimSpace(parts[1])
					vramBytes, _ := strconv.ParseInt(strings.TrimSpace(parts[2]), 10, 64)
					if name != "" {
						gpus = append(gpus, GPUInfo{
							Name:   name,
							VRAMGB: float64(vramBytes) / (1024 * 1024 * 1024),
						})
					}
				}
			}
		}

	case "linux":
		// 尝试 lspci
		out, err := exec.Command("lspci", "-mm").Output()
		if err == nil {
			lines := strings.Split(string(out), "\n")
			for _, line := range lines {
				if strings.Contains(strings.ToLower(line), "vga") || strings.Contains(strings.ToLower(line), "3d") {
					parts := strings.Split(line, "\"")
					if len(parts) >= 4 {
						gpus = append(gpus, GPUInfo{Name: parts[3], VRAMGB: 0})
					}
				}
			}
		}

	case "macos":
		out, err := exec.Command("system_profiler", "SPDisplaysDataType", "-json").Output()
		if err == nil {
			// 简单解析 JSON 中的 _name 字段
			var result map[string]interface{}
			if json.Unmarshal(out, &result) == nil {
				if arr, ok := result["SPDisplaysDataType"].([]interface{}); ok {
					for _, item := range arr {
						if m, ok := item.(map[string]interface{}); ok {
							if name, ok := m["_name"].(string); ok {
								gpus = append(gpus, GPUInfo{Name: name, VRAMGB: 0})
							}
						}
					}
				}
			}
		}
	}

	return gpus
}

func detectStorage() StorageInfo {
	s := StorageInfo{}
	var stat syscall.Statfs_t
	wd, _ := os.Getwd()
	if err := syscall.Statfs(wd, &stat); err == nil {
		total := stat.Blocks * uint64(stat.Bsize)
		avail := stat.Bavail * uint64(stat.Bsize)
		s.TotalGB = float64(total) / (1024 * 1024 * 1024)
		s.AvailableGB = float64(avail) / (1024 * 1024 * 1024)
	}
	return s
}

func gpuFingerprint(gpus []GPUInfo) string {
	names := []string{}
	for _, g := range gpus {
		names = append(names, g.Name)
	}
	return strings.Join(names, "|")
}

func recommendTier(mem MemoryInfo, gpus []GPUInfo) string {
	totalVRAM := 0.0
	for _, g := range gpus {
		totalVRAM += g.VRAMGB
	}

	switch {
	case mem.TotalGB >= 64 || totalVRAM >= 48:
		return "ULTRA"
	case mem.TotalGB >= 32 || totalVRAM >= 24:
		return "PRO"
	case mem.TotalGB >= 16 || totalVRAM >= 8:
		return "STANDARD"
	case mem.TotalGB >= 8:
		return "LITE"
	default:
		return "API_MODE"
	}
}

// ==================== 硬件档案管理 ====================

func updateHardwareProfile(rootDir string, profile DeviceProfile) error {
	path := filepath.Join(rootDir, profilePath)
	_ = os.MkdirAll(filepath.Dir(path), 0755)

	var hw HardwareProfile
	data, err := os.ReadFile(path)
	if err == nil && len(data) > 0 {
		_ = json.Unmarshal(data, &hw)
	} else {
		hw.Version = "1.0"
		hw.Profiles = []DeviceProfile{}
	}

	// 查找是否已存在
	found := false
	for i, p := range hw.Profiles {
		if p.ID == profile.ID {
			// 更新动态字段
			hw.Profiles[i].LastSeen = profile.LastSeen
			hw.Profiles[i].Memory.AvailableGB = profile.Memory.AvailableGB
			hw.Profiles[i].Storage.AvailableGB = profile.Storage.AvailableGB
			// 如果硬件升级了，更新静态字段
			hw.Profiles[i].Memory.TotalGB = profile.Memory.TotalGB
			hw.Profiles[i].GPUs = profile.GPUs
			hw.Profiles[i].CPU = profile.CPU
			found = true
			break
		}
	}

	if !found {
		hw.Profiles = append(hw.Profiles, profile)
	}

	data, err = json.MarshalIndent(hw, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// ==================== 进程与浏览器 ====================

func startProcess(bin string, args []string, env []string, dir string) (*exec.Cmd, error) {
	cmd := exec.Command(bin, args...)
	cmd.Env = env
	cmd.Dir = dir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	// Windows: 创建新进程组，避免 Ctrl+C 穿透
	if runtime.GOOS == "windows" {
		cmd.SysProcAttr = &syscall.SysProcAttr{
			CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP,
		}
	}

	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return cmd, nil
}

func killProcess(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	if runtime.GOOS == "windows" {
		// Windows 发送 CTRL_BREAK_EVENT
		_ = cmd.Process.Kill()
	} else {
		_ = cmd.Process.Signal(syscall.SIGTERM)
		// 给 2 秒优雅退出
		done := make(chan error, 1)
		go func() { done <- cmd.Wait() }()
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			_ = cmd.Process.Kill()
		}
	}
}

func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("cmd", "/c", "start", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}

func fatal(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "[Fatal] "+format+"\n", args...)
	os.Exit(1)
}
一个封装在移动硬盘中的完整 AI Space 生态系统 - Starry Space 。无需安装，无需配置，插入即运行。根据接入设备的硬件配置和系统配置自动启动对应的python编译器和llama.cpp。模型由用户选择，但是系统会根据配置信息推荐，从笔记本到服务器，从 4B 到 70B+，无缝适配。

模型层级：
ULTRA
PRO
STANDARD
LITE
MULTIMODAL
EMBEDDING

即插即用开源移动硬盘项目Starry Space功能说明：
跨平台（Win/Mac/Linux）跨架构（x86_64/arm64）启动
自动硬件和系统检测
提供模型下载与安装
提供模型convert-to-guff服务
本地AI推理（llama.cpp，通过llama-server调用）
可设置API连接云端大模型
RAG数据库
联网能力（调用API）
多轮对话
Agent能力
WebUI FASTAPI+React
模型训练+微调 - Unsloth Python


Starry Space Modes:
1. 快速模式
2. 深度思考
3. Agent Space -> 每开启一个Agent下开设一个文件夹进行具体项目执行
4. Starry Claw -> 启动时作为本地化自托管智能体（需要持续接入设备）

Workshop:
1. Training
2. Tuning
3. Agent-Design
4. Skill-Design

你能帮我写启动器吗？不需要python备用启动器，你帮我写个go吧starry-windows.exe和starry-linux和starry-macos这三个放在starry-space根目录。我已经下载了uv和python-standalone版本（如下架构），请你不要再用venv了，因为venv是一定要用绝对路径的，但是我会插到不同设备，会出现问题。
每个启动器的逻辑
1. 检测系统和架构
2. 检测硬件信息和设备信息
3. 生成/加载 hardware-profile.json（注意这个json是可以存很多个设备信息的，所以每次生成是增加json，不做删减）
4. 启动对应的runtime
5. 启动starry-core
6. 启动webui
7. 浏览器自动打开localhost:xxxx


以下是我设计的项目结构
starry-space/
├── starry-windows.exe
├── starry-linux
├── starry-macos
├── README.md
├── LICENSE (MIT)
├── launcher/
│   └── main.go 
│
├── runtime/
│   ├── uv-windows-x86_64.exe
│   ├── uv-windows-aarch64.exe
│   ├── uv-linux-x86_64
│   ├── uv-linux-aarch64
│   ├── uv-macos-x86_64
│   ├── uv-macos-aarch64
│   ├── cpython/
│   │   ├── cpython-3.13.14-linux-aarch64-gnu/
│   │   │   ├── bin/
│   │   │   │   ├── python
│   │   │   │   └──...
│   │   │   ├── lib/
│   │   │   └── ...
│   │   ├── cpython-3.13.14-linux-x86_64-gnu/
│   │   │   ├── bin/
│   │   │   │   ├── python
│   │   │   │   └──...
│   │   │   ├── lib/
│   │   │   └── ...
│   │   ├── cpython-3.13.14-macos-aarch64-none/
│   │   │   ├── bin/
│   │   │   │   ├── python
│   │   │   │   └──...
│   │   │   ├── lib/
│   │   │   └── ...
│   │   ├── cpython-3.13.14-macos-x86_64-none/
│   │   │   ├── bin/
│   │   │   │   ├── python
│   │   │   │   └──...
│   │   │   ├── lib/
│   │   │   └── ...
│   │   ├── cpython-3.13.14-windows-aarch64-none/
│   │   │   ├── Lib/
│   │   │   ├── python.exe
│   │   │   └── ...
│   │   └── cpython-3.13.14-windows-x86_64-none/
│   │       ├── Lib/
│   │       ├── python.exe
│   │       └── ...
│   └── requirements.txt
│
├── model-center/
│   ├── registry.json
│   ├── guff-models/
│   │   ├── 
│   │   └── 
│   └── comfyui-models/
├── model-engine/
│   ├── llama.cpp/
│   │   ├── llama-b9839-bin-win-cuda-13.3-x64/
│   │   │   ├── llama-server.exe
│   │   │   └── ...
│   │   └── ...
│   ├── ComfyUI-Portable/
│   │   └── ComfyUI_windows_portable_nvidia/
│   │       └── ComfyUI/
│   │           └── extra_model_paths.yaml
│   └── ...
│
├── starry-core/
│   ├── __init__.py
│   ├── main.py
│   ├── modes/
│   │   ├── chat.py
│   │   ├── deepthink.py
│   │   ├── agent_space.py
│   │   └── starry_claw.py
│   ├── workshops/
│   │   ├── training.py
│   │   ├── tuning.py
│   │   ├── agent_desgin.py
│   │   └── skill_design.py
│   ├── inference/
│   │   ├── engine_base.py
│   │   ├── llama_cpp_engine.py
│   │   ├── comfyui_engine.py
│   │   └── api_engine.py
│   ├── rag/
│   │   ├── vector_store.py
│   │   ├── document_loader.py
│   │   └── retriever.py
│   ├── agent_framework/
│   │   ├── agent_base.py
│   │   ├── tool_registery.py
│   │   └── planner.py
│   └── hardware/
│       ├── profiler.py
│       └── gpu_utils.py
│
├── starry-webui/
│   ├── .gitignore
│   ├── .oxlintrc.json
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   │
│   ├── node_modules/
│   │   ├── .bin
│   │   ├── .vite
│   │   ├── @alloc
│   │   └── ...
│   │
│   ├── public/
│   │   ├── favicon.png
│   │   └── favicon.svg
│   │
│   └── src/
│       ├── App.css
│       ├── App.tsx
│       ├── main.tsx
│       ├── index.tsx
│       ├── components/
│       ├── pages/
│       │   ├── 
│       │   ├── 
│       │   └── asset/
│       ├── 
│       ├── 
│       ├── 
│       ├── 
│       ├── 
│       ├── 
│       └── asset/
│
├── config/
├── data/
├── logs/
└── update/
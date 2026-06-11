# AI 伴侣 — Kivy + Talkify TTS

基于 Kivy 框架的 AI 伴侣 Android 应用，通过 **[Talkify TTS](https://github.com/LonePheasantWarrior/TalkifyTTS)** 云端语音引擎实现 TTS 朗读。

## 架构

```
┌────────────────────────────────────────┐
│  AI 伴侣 (Kivy APK)                     │
│  ├── Chat UI (Kivy)                    │
│  ├── pyjnius → Android TTS API         │
│  └── LLM API 调用 (待接入)             │
└────────────┬───────────────────────────┘
             │ Android TTS API
             ▼
┌────────────────────────────────────────┐
│  Talkify TTS (独立 APK)                │
│  ├── 微软 Azure TTS                    │
│  ├── 通义千问 Qwen3-TTS                │
│  ├── 豆包 SeedTTS2                     │
│  ├── 腾讯云 TTS                        │
│  ├── MiniMax TTS                       │
│  └── 小米米萌 TTS                      │
└────────────────────────────────────────┘
```

## 功能

- 💬 简洁的聊天界面（用户/AI 气泡）
- 🔊 一键开关 TTS 语音朗读
- ☁️ 支持 6 个云端 TTS 引擎（由 Talkify 提供）
- 📱 Android 11+ (API 30+)

## 前置条件

1. **安装 Talkify APK**：将 `Talkify-release_1.0.26.apk` 安装到 Android 设备
2. **设为默认 TTS**：系统设置 → 语言和输入法 → 文字转语音 → 选择 "Talkify"
3. **在 Talkify 中配置引擎**：打开 Talkify 应用，选择和配置想要的云端 TTS 引擎

## 构建 APK

### 在 Linux / WSL 上构建

```bash
# 1. 安装 Buildozer 依赖
sudo apt update
sudo apt install -y python3-pip openjdk-17-jdk autoconf libtool \
    libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev \
    libffi-dev libsqlite3-dev cmake zip unzip git

pip3 install buildozer cython virtualenv

# 2. 构建 APK（首次约 20-40 分钟，需要下载 SDK/NDK）
buildozer android debug

# 3. APK 输出位置
ls -la bin/*.apk
```

### 在 macOS 上构建

```bash
# 同样的步骤，但依赖不同
brew install python3 openjdk@17 autoconf automake libtool
pip3 install buildozer
buildozer android debug
```

## 目录结构

```
AIAssistant/
├── main.py              # Kivy 主程序（含 TTS 集成）
├── buildozer.spec       # Buildozer 安卓打包配置
├── requirements.txt     # Python 依赖
├── assets/              # 资源文件
└── bin/                 # 构建输出（buildozer 生成）
```

## TTS 工作流程

```python
# main.py 中的 TTS 调用
from jnius import autoclass
TextToSpeech = autoclass('android.speech.tts.TextToSpeech')

# 初始化
tts = TextToSpeech(activity, on_init_callback)
tts.setLanguage(Locale.CHINESE)

# 朗读 — Android 自动路由到 Talkify
tts.speak("你好世界", TextToSpeech.QUEUE_FLUSH, params, "utterance_id")
```

Talkify 对 TTS API 调用者完全透明——无需任何特殊配置。

## TODO

- [ ] 接入 LLM API（OpenAI / Qwen / DeepSeek）
- [ ] 语音输入（STT）
- [ ] 对话历史持久化
- [ ] 自定义角色/人格

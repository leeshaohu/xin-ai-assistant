[app]

# (str) Title of your application
title = 心语 AI 陪伴

# (str) Package version
version = 0.1

# (str) Package name
package.name = aiassistant

# (str) Package domain (needed for android/ios packaging)
package.domain = com.lonepheasantwarrior

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (let empty to include all files)
source.include_exts = py,png,jpg,kv,atlas,ttf,json,txt,.html

# (list) Application requirements
# pyjnius = Android TTS API access
# kivy = UI framework
# plyer = audio playback support
requirements = python3,kivy==2.2.1,pyjnius,plyer

# (str) Custom source folders for requirements
# requirements.source.kivy = ../../kivy

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) Permissions
# INTERNET = DeepSeek API + Edge-TTS
# MODIFY_AUDIO_SETTINGS = TTS audio output
# WAKE_LOCK = keep screen on during TTS
# FOREGROUND_SERVICE = Android 8+ required for background
# POST_NOTIFICATIONS = Android 13+ notification permission
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,MODIFY_AUDIO_SETTINGS,WAKE_LOCK,FOREGROUND_SERVICE,POST_NOTIFICATIONS

# (int) Target Android API
android.api = 34

# (int) Minimum API your APK will support (26 = Android 8.0)
android.minapi = 26

# (int) NDK version (25b = r25b, required for arm64-v8a)
android.ndk = 25b

# (str) Android SDK directory (auto-detect if empty)
# android.sdk_path = 

# (list) Android architectures to build for
# arm64-v8a = 64-bit (modern devices, smaller APK)
android.archs = arm64-v8a

# (int) Android SDK to compile against
android.compile_sdk_version = 34

# ============================================================================
# Python for Android (p4a) specific
# ============================================================================

# (str) bootstrap — sdl2 is the standard Kivy bootstrap
p4a.bootstrap = sdl2

# (str) python-for-android branch — master = stable
p4a.branch = master

# ============================================================================
# Packaging
# ============================================================================

# (bool) Skip package update
# android.skip_update = False

# (bool) Indicate whether the app should be fullscreen or not
fullscreen = 0

# (str) Presplash image (shown during load)
# presplash.filename = assets/presplash.png

# (str) Icon image
# icon.filename = assets/icon.png

# (bool) Whether to use Android App Bundle (aab = Play Store only)
# apk = direct install, aab = Google Play only
android.release_artifact = apk

# ============================================================================
# Log and debugging
# ============================================================================

# (str) Log level: trace, debug, info, warning, error, critical
log_level = 2

# (bool) Allow wake locks (keep screen on)
android.wakelock = True

# ============================================================================
# Advanced
# ============================================================================

# (bool) Enable AndroidX
android.enable_androidx = True

# (list) Patterns to exclude from the APK
# android.exclude =

# (list) Patterns of files to exclude from APK (space-separated)
# android.exclude_patterns =

# ============================================================================
# Talkify TTS Integration Notes
# ============================================================================
#
# 本应用使用 Kivy WebView 加载 chat.html，TTS 通过 pyjnius 直连 Android TTS API。
# WebViewClient 拦截 tts:// 协议 → 调用 TextToSpeech.speak() → Talkify 云端引擎。
#
# 用户需要：
#   1. 安装 Talkify APK (Talkify-release_1.0.26.apk)
#   2. 系统设置 → 语言和输入法 → 文字转语音 → 选择 "Talkify"
#
# 音频保存架构：
#   chat.html → Kivy WebView → save-tts:// 协议
#     → NativeTTS.synthesizeToFile() → WAV 文件保存到磁盘
#
# ============================================================================

#!/bin/bash
# ═══════════════════════════════════════════════
#  心语 AI 助手 — APK 构建脚本（国内镜像加速版）
#  适用于 WSL Ubuntu / Debian / 原生 Linux
# ═══════════════════════════════════════════════
set -e
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ═══════════════════════════════════════════════
# 0. 镜像配置
# ═══════════════════════════════════════════════
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

# 国内 NDK (r25b) — 腾讯云镜像
NDK_URL="https://mirrors.cloud.tencent.com/android/repository/android-ndk-r25b-linux.zip"
NDK_FILE="android-ndk-r25b-linux.zip"

# Android 命令行工具
SDK_CMDLINE_URL="https://mirrors.cloud.tencent.com/android/repository/commandlinetools-linux-11076708_latest.zip"

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║   心语 AI 助手 APK 构建工具（镜像版）   ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════
# 1. 安装系统依赖
# ═══════════════════════════════════════════════
log "第 1 步：安装系统依赖..."

if [ -f /etc/debian_version ]; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        python3-pip python3-dev python3-setuptools \
        git zip unzip openjdk-17-jdk-headless \
        autoconf libtool pkg-config zlib1g-dev \
        libncurses5-dev libncursesw5-dev libtinfo5 \
        cmake libffi-dev libssl-dev \
        ccache
else
    warn "非 Debian 系统，请手动安装：python3-pip git zip unzip openjdk-17-jdk"
fi

log "系统依赖安装完成"

# ═══════════════════════════════════════════════
# 2. 配置 pip 镜像 + 安装 Buildozer
# ═══════════════════════════════════════════════
log "第 2 步：安装 Buildozer（清华镜像）..."

python3 -m pip install --upgrade pip -i "$PIP_MIRROR" -q
python3 -m pip install buildozer cython==0.29.33 -i "$PIP_MIRROR" -q

log "Buildozer 安装完成"

# ═══════════════════════════════════════════════
# 3. 预下载 Android NDK（国内镜像）
# ═══════════════════════════════════════════════
log "第 3 步：下载 Android NDK r25b（腾讯云镜像）..."
mkdir -p ~/.buildozer/android/platform

NDK_DIR="$HOME/.buildozer/android/platform/android-ndk-r25b"
if [ ! -d "$NDK_DIR" ]; then
    cd /tmp
    if [ ! -f "$NDK_FILE" ]; then
        log "正在下载 NDK (~150MB，约 1-2 分钟)..."
        wget -q --show-progress "$NDK_URL" -O "$NDK_FILE" || \
        curl -L --progress-bar "$NDK_URL" -o "$NDK_FILE"
    fi
    log "正在解压 NDK..."
    unzip -qo "$NDK_FILE" -d ~/.buildozer/android/platform/
    rm -f "$NDK_FILE"
    log "NDK 安装完成"
else
    log "NDK 已存在，跳过"
fi

# ═══════════════════════════════════════════════
# 4. 预下载 Android SDK 命令行工具
# ═══════════════════════════════════════════════
SDK_DIR="$HOME/.buildozer/android/platform/android-sdk"
if [ ! -d "$SDK_DIR/cmdline-tools" ]; then
    log "下载 Android SDK 命令行工具..."
    cd /tmp
    wget -q --show-progress "$SDK_CMDLINE_URL" -O "cmdline-tools.zip" 2>/dev/null || \
    curl -L --progress-bar "$SDK_CMDLINE_URL" -o "cmdline-tools.zip"
    
    mkdir -p "$SDK_DIR/cmdline-tools"
    unzip -qo "cmdline-tools.zip" -d "$SDK_DIR/cmdline-tools/"
    rm -f "cmdline-tools.zip"
    
    # 用 SDK Manager 安装必要组件
    export ANDROID_SDK_ROOT="$SDK_DIR"
    yes | $SDK_DIR/cmdline-tools/cmdline-tools/bin/sdkmanager --sdk_root="$SDK_DIR" \
        "platform-tools" "platforms;android-34" "build-tools;34.0.0" 2>/dev/null || true

    log "Android SDK 安装完成"
else
    log "Android SDK 已存在，跳过"
fi

# ═══════════════════════════════════════════════
# 5. 更新 buildozer.spec（确保 NDK/SDK 路径正确）
# ═══════════════════════════════════════════════
log "第 5 步：配置 buildozer.spec..."

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 更新 NDK 路径
if grep -q "^android.ndk_path" buildozer.spec; then
    sed -i "s|^android.ndk_path.*|android.ndk_path = $NDK_DIR|" buildozer.spec
else
    echo "android.ndk_path = $NDK_DIR" >> buildozer.spec
fi

# 更新 SDK 路径
if grep -q "^android.sdk_path" buildozer.spec; then
    sed -i "s|^android.sdk_path.*|android.sdk_path = $SDK_DIR|" buildozer.spec
else
    echo "android.sdk_path = $SDK_DIR" >> buildozer.spec
fi

log "配置完成"

# ═══════════════════════════════════════════════
# 6. 开始构建 APK
# ═══════════════════════════════════════════════
log "第 6 步：开始构建 APK..."
echo ""
echo "  ⏱  预计 10-20 分钟（首次构建下载多）"
echo "  📦 APK 将生成在: $PROJECT_DIR/bin/"
echo ""
echo "═══════════════════════════════════════════════"

# 清理旧构建（可选）
# buildozer android clean

# 使用 pip 镜像加速 python-for-android 的包下载
buildozer android debug \
    --extra-pip-args="--index-url $PIP_MIRROR --trusted-host pypi.tuna.tsinghua.edu.cn"

# ═══════════════════════════════════════════════
# 7. 完成
# ═══════════════════════════════════════════════
APK_FILE=$(ls bin/*.apk 2>/dev/null | head -1)
if [ -n "$APK_FILE" ]; then
    echo ""
    echo "╔═══════════════════════════════════════════════════╗"
    echo "║          🎉 APK 构建成功！                        ║"
    echo "╠═══════════════════════════════════════════════════╣"
    echo "║  📱 $APK_FILE"
    echo "║  📏 $(du -sh "$APK_FILE" | cut -f1)"
    echo "║                                                    "
    echo "║  安装到手机：                                       "
    echo "║  1. 把 APK 传送到手机                              "
    echo "║  2. 手机打开 APK 文件安装                          "
    echo "║  3. 确保已安装 Talkify APK                        "
    echo "╚═══════════════════════════════════════════════════╝"
else
    err "构建失败，请检查上方错误信息"
fi

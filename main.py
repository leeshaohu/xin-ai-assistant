"""
心语 AI 陪伴助手 — Kivy WebView + 原生 TTS（Talkify）
========================================================
架构：
  chat.html（聊天UI）→ Kivy WebView 加载
  TTS：pyjnius → android.speech.tts.TextToSpeech → Talkify（系统TTS引擎）
  桥接：WebViewClient 拦截 tts:// 协议 → 调用原生TTS
"""

import os
import sys
import base64
from urllib.parse import urlparse, unquote, parse_qs

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.core.window import Window

# ============================================================
#  Android 原生层
# ============================================================
IS_ANDROID = hasattr(sys, 'getandroidapilevel')

if IS_ANDROID:
    from jnius import autoclass, PythonJavaClass, java_method

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    WebView        = autoclass('android.webkit.WebView')
    WebViewClient  = autoclass('android.webkit.WebViewClient')
    WebSettings    = autoclass('android.webkit.WebSettings')
    TextToSpeech   = autoclass('android.speech.tts.TextToSpeech')
    Locale         = autoclass('java.util.Locale')
    Bundle         = autoclass('android.os.Bundle')
    JavaFile       = autoclass('java.io.File')
    ViewGroup_LP   = autoclass('android.view.ViewGroup$LayoutParams')
    FrameLayout    = autoclass('android.widget.FrameLayout')
    Color          = autoclass('android.graphics.Color')
    Handler        = autoclass('android.os.Handler')
    Looper         = autoclass('android.os.Looper')
    Uri            = autoclass('android.net.Uri')


# ============================================================
#  TTS 桥
# ============================================================
class NativeTTS:
    """Android 原生 TTS — 通过系统引擎（Talkify）朗读"""
    def __init__(self, webview):
        self.wv = webview
        self.tts = None
        self.ready = False
        self._init_tts()

    def _init_tts(self):
        if not IS_ANDROID:
            return
        activity = PythonActivity.mActivity
        self.main_handler = Handler(Looper.getMainLooper())

        def on_init(status):
            self.ready = (status == TextToSpeech.SUCCESS)
            if self.ready:
                result = self.tts.setLanguage(Locale.CHINESE)
                if result in (TextToSpeech.LANG_MISSING_DATA,
                              TextToSpeech.LANG_NOT_SUPPORTED):
                    self.tts.setLanguage(Locale.US)
                self.tts.setOnUtteranceProgressListener(
                    self._make_progress_listener()
                )
                print('[TTS] Talkify 引擎就绪')
            else:
                print(f'[TTS] 初始化失败 status={status}')

        self.tts = TextToSpeech(activity, on_init)

    def _make_progress_listener(self):
        """创建 UtteranceProgressListener，TTS 结束后通知 WebView"""
        class ProgressListener(PythonJavaClass):
            __javainterfaces__ = ['android/speech/tts/UtteranceProgressListener']

            def __init__(self, wv, handler):
                super().__init__()
                self.wv = wv
                self.handler = handler

            @java_method('(Ljava/lang/String;)V')
            def onStart(self, utteranceId):
                pass

            @java_method('(Ljava/lang/String;)V')
            def onDone(self, utteranceId):
                uid = str(utteranceId) if utteranceId else ''
                if uid.startswith('save_'):
                    # ★ synthesizeToFile 完成 → 通知 JS 文件已保存
                    # utteranceId 格式: save_{hidx}_{timestamp}
                    parts = uid.split('_')
                    hidx = parts[1] if len(parts) > 1 else '-1'
                    def notify():
                        self.wv.evaluateJavascript(
                            f'window.__onTTSFileSaved({hidx})', None)
                    self.handler.post(notify)
                else:
                    # 正常 TTS 播放结束 → 通知 JS 端
                    def notify():
                        self.wv.evaluateJavascript('window.__onTTSEnd()', None)
                    self.handler.post(notify)

            @java_method('(Ljava/lang/String;)V')
            def onError(self, utteranceId):
                def notify():
                    self.wv.evaluateJavascript('window.__onTTSEnd()', None)
                self.handler.post(notify)

            @java_method('(Ljava/lang/String;II)V')
            def onError(self, utteranceId, errorCode):
                def notify():
                    self.wv.evaluateJavascript('window.__onTTSEnd()', None)
                self.handler.post(notify)

            @java_method('(Ljava/lang/String;III)V')
            def onStop(self, utteranceId, interrupted):
                pass

        return ProgressListener(self.wv, self.main_handler)

    def speak(self, text: str):
        if not self.ready or not self.tts:
            print('[TTS] 引擎未就绪')
            return
        params = Bundle()
        result = self.tts.speak(text, TextToSpeech.QUEUE_FLUSH, params,
                                f"xinyu_tts_{hash(text)}")
        if result != TextToSpeech.SUCCESS:
            print(f'[TTS] speak 失败: {result}')

    def stop(self):
        if self.tts and self.ready:
            self.tts.stop()

    def shutdown(self):
        if self.tts:
            self.tts.stop()
            self.tts.shutdown()


# ============================================================
#  WebView 桥接客户端
# ============================================================
if IS_ANDROID:

    class TTSWebViewClient(PythonJavaClass):
        """拦截 tts:// 协议 → 调用原生 TTS"""
        __javainterfaces__ = ['android/webkit/WebViewClient']

        def __init__(self, tts_bridge):
            super().__init__()
            self.tts = tts_bridge
            self._injected = False

        @java_method('(Landroid/webkit/WebView;Ljava/lang/String;)V')
        def onPageFinished(self, wv, url):
            """页面加载完成 → 注入 TTS 桥到 JS 上下文"""
            if self._injected:
                return
            self._injected = True
            print('[WebView] onPageFinished 触发, URL={}, 开始注入 __nativeTTS__'.format(url))
            # 注入 window.__nativeTTS__ = { speak, stop }
            js = """
            (function(){
                var id = 'tts_iframe_' + Date.now();
                window.__nativeTTS__ = {
                    speak: function(text) {
                        var iframe = document.getElementById(id);
                        if (!iframe) {
                            iframe = document.createElement('iframe');
                            iframe.id = id;
                            iframe.style.display = 'none';
                            document.body.appendChild(iframe);
                        }
                        iframe.src = 'tts://speak?text=' + encodeURIComponent(text);
                    },
                    stop: function() {
                        var iframe = document.getElementById(id);
                        if (iframe) iframe.src = 'tts://stop';
                    }
                };
                console.log('[NativeTTS] bridge injected ✓');
                '__nativeTTS_injected_ok';
            });
            """

            def onInjectResult(result):
                r = str(result) if result else '(null)'
                if 'Error' in r or 'error' in r:
                    print('[WebView] ❌ JS注入失败: {}'.format(r))
                else:
                    print('[WebView] ✅ JS注入成功: {}'.format(r))

            wv.evaluateJavascript(js, onInjectResult)

        @java_method('(Landroid/webkit/WebView;Ljava/lang/String;)Z')
        def shouldOverrideUrlLoading(self, wv, url):
            """拦截 tts:// 和 save:// 协议 URL"""
            # ── TTS 协议 ──
            if url.startswith('tts://'):
                print('[TTS-Bridge] 拦截到 tts:// URL: {}'.format(url[:80]))
                try:
                    parsed = urlparse(url)
                    if parsed.path.startswith('/speak'):
                        query = parsed.query
                        if 'text=' in query:
                            text = unquote(query.split('text=')[1].split('&')[0])
                            self.tts.speak(text)
                    elif parsed.path.startswith('/stop'):
                        self.tts.stop()
                except Exception as e:
                    print(f'[TTS-Bridge] Error: {e}')
                return True

            # ── 音频保存协议（Edge-TTS 生成 MP3 的 base64 数据）──
            if url.startswith('save://audio'):
                try:
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    path = params.get('path', [''])[0]
                    name = params.get('name', ['心语_tts.mp3'])[0]
                    data_b64 = params.get('data', [''])[0]
                    if path and data_b64:
                        audio_bytes = base64.b64decode(data_b64)
                        save_dir = path.rstrip('/')
                        os.makedirs(save_dir, exist_ok=True)
                        save_path = os.path.join(save_dir, name)
                        with open(save_path, 'wb') as f:
                            f.write(audio_bytes)
                        print(f'[Save-Audio] 已保存: {save_path} ({len(audio_bytes)} bytes)')
                except Exception as e:
                    print(f'[Save-Audio] Error: {e}')
                return True

            # ── 原生 TTS 保存协议（Android Talkify 直接合成到文件）──
            if url.startswith('save-tts://'):
                print('[Save-TTS] 拦截到 save-tts:// URL: {}'.format(url[:100]))
                try:
                    import time
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    text = params.get('text', [''])[0]
                    path = params.get('path', [''])[0]
                    name = params.get('name', ['心语_tts.wav'])[0]
                    hidx = params.get('hidx', ['-1'])[0]

                    if text and path and self.tts and self.tts.ready:
                        save_dir = path.rstrip('/')
                        os.makedirs(save_dir, exist_ok=True)
                        save_path = os.path.join(save_dir, name)
                        save_file = JavaFile(save_path)
                        uid = 'save_{}_{}'.format(hidx, int(time.time() * 1000))

                        # ★ synthesizeToFile 必须在主线程调用
                        def do_synthesize():
                            result = self.tts.tts.synthesizeToFile(
                                text, Bundle(), save_file, uid
                            )
                            if result != TextToSpeech.SUCCESS:
                                print('[Save-TTS] synthesizeToFile 失败: result={}'.format(result))
                                # 通知 JS 保存失败
                                def notify_fail():
                                    self.wv.evaluateJavascript(
                                        'window.__onTTSFileSaved({}, true)'.format(hidx),
                                        None
                                    )
                                self.tts.main_handler.post(notify_fail)
                        self.tts.main_handler.post(do_synthesize)
                        print('[Save-TTS] 已提交 synthesizeToFile 请求: {}'.format(save_path))
                except Exception as e:
                    print('[Save-TTS] Error: {}'.format(e))
                return True

            return False

        @java_method('(Landroid/webkit/WebView;Landroid/net/http/SslError;Landroid/os/Handler;)V')
        def onReceivedSslError(self, view, handler, error):
            # 本地 file:// 不需要 SSL
            pass


# ============================================================
#  Kivy App
# ============================================================
class XinyuApp(App):
    def build(self):
        Window.clearcolor = (0.95, 0.94, 0.92, 1)
        Window.softinput_mode = 'below_target'

        if not IS_ANDROID:
            # 桌面端：直接在浏览器打开 chat.html
            import webbrowser
            html_path = os.path.join(os.path.dirname(__file__), 'chat.html')
            webbrowser.open('file://' + html_path)
            print('[Desktop] 已在浏览器中打开 chat.html')
            print('[Desktop] TTS 使用 Web Speech API（桌面语音引擎）')
            return Widget()

        # Android: 延时初始化 WebView（等 Kivy 窗口就绪）
        Clock.schedule_once(self._init_webview, 0.3)
        return Widget()

    def _init_webview(self, dt):
        activity = PythonActivity.mActivity

        # 1. 创建 WebView
        wv = WebView(activity)
        wv.setBackgroundColor(Color.argb(0, 245, 240, 235))
        settings = wv.getSettings()
        settings.setJavaScriptEnabled(True)
        settings.setDomStorageEnabled(True)
        settings.setAllowFileAccess(True)
        settings.setLoadWithOverviewMode(True)
        settings.setUseWideViewPort(True)
        settings.setSupportZoom(False)
        settings.setBuiltInZoomControls(False)
        settings.setDisplayZoomControls(False)
        # 允许混合内容（file:// 加载 https:// 资源）
        if hasattr(settings, 'setMixedContentMode'):
            settings.setMixedContentMode(0)  # MIXED_CONTENT_ALWAYS_ALLOW

        # 2. TTS 桥
        self.tts = NativeTTS(wv)

        # 3. WebViewClient（拦截 tts:// + 注入 JS 桥）
        wv.setWebViewClient(TTSWebViewClient(self.tts))

        # 4. 加载 chat.html（从 app 目录读取，用 loadDataWithBaseURL）
        html_path = os.path.join(os.path.dirname(__file__), 'chat.html')
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            wv.loadDataWithBaseURL(
                'file:///android_asset/',
                html_content,
                'text/html',
                'UTF-8',
                None
            )
            print(f'[WebView] 已加载 chat.html ({len(html_content)} 字符)')
        except FileNotFoundError:
            wv.loadUrl('about:blank')
            print('[WebView] chat.html 未找到！')

        # 5. 将 WebView 添加到 Activity（全屏覆盖 Kivy 窗口）
        params = FrameLayout.LayoutParams(
            ViewGroup_LP.MATCH_PARENT,
            ViewGroup_LP.MATCH_PARENT
        )
        activity.addContentView(wv, params)
        self.webview = wv

    def on_stop(self):
        if hasattr(self, 'tts'):
            self.tts.shutdown()


# ============================================================
#  入口
# ============================================================
if __name__ == '__main__':
    XinyuApp().run()

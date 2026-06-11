"""
火山引擎 TTS 代理 — 部署到 Vercel (免费、快速)
解决浏览器 CORS 问题: chat.html → 本代理 → 火山引擎 API v3

请求格式: POST /api/tts_proxy  { apiKey, voice, text }
返回格式: audio/wav
"""
import json
import struct
import base64
from http.server import BaseHTTPRequestHandler

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Function — 火山引擎 TTS 代理"""

    def do_OPTIONS(self):
        """CORS 预检"""
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        """转发 TTS 请求到火山引擎"""
        if self.path not in ('/api/tts_proxy', '/tts_proxy', '/'):
            self.send_response(404)
            self._cors()
            self.end_headers()
            return

        try:
            # 读取请求体
            cl = int(self.headers.get('Content-Length', 0))
            if cl == 0:
                self._err(400, '空请求体')
                return
            data = json.loads(self.rfile.read(cl))

            apiKey = data.get('apiKey', '')
            voice  = data.get('voice', 'zh_female_vv_uranus_bigtts')
            text   = data.get('text', '').strip()

            if not apiKey:
                self._err(400, '缺少 apiKey (火山引擎 API Key)')
                return
            if not text:
                self._err(400, '缺少 text (文本内容)')
                return

            # ── 拼接火山引擎 API v3 请求（完全对齐 Talkify SeedTts2Engine）──
            volc_body = {
                "user": {"uid": "xinyu_user_"},
                "req_params": {
                    "text": text,
                    "speaker": voice,
                    "audio_params": {
                        "format": "pcm",
                        "sample_rate": 24000,
                        "speech_rate": 0,
                        "loudness_rate": 0,
                    },
                    "additions": json.dumps({
                        "explicit_language": "zh",
                        "disable_markdown_filter": True,
                    }),
                },
            }

            volc_headers = {
                'Content-Type': 'application/json',
                'x-api-key': apiKey,
                'X-Api-Resource-Id': 'seed-tts-2.0',
                'Connection': 'keep-alive',
            }

            volc_url = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'

            # ── 发送请求 + 解析 NDJSON 流式响应 ──
            if HAS_HTTPX:
                wav = self._req_httpx(volc_url, volc_headers, volc_body)
            else:
                wav = self._req_urllib(volc_url, volc_headers, volc_body)

            if isinstance(wav, dict):
                # 返回的是错误
                self._err(wav.get('status', 500), wav.get('error', '未知错误'))
                return

            # ── 返回 WAV ──
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)

        except json.JSONDecodeError:
            self._err(400, 'JSON 解析失败')
        except Exception as e:
            self._err(500, str(e)[:200])

    # ═══════════════════════════════════════
    #  httpx 方式（Vercel 上会自动装）
    # ═══════════════════════════════════════
    def _req_httpx(self, url, headers, body):
        with httpx.Client(timeout=30.0) as client:
            with client.stream('POST', url, json=body, headers=headers) as r:
                if r.status_code != 200:
                    err = r.read().decode('utf-8', errors='replace')[:500]
                    return {'status': r.status_code, 'error': f'火山引擎 {r.status_code}: {err}'}
                return self._parse_ndjson(r)

    # ═══════════════════════════════════════
    #  urllib 方式（本地测试用）
    # ═══════════════════════════════════════
    def _req_urllib(self, url, headers, body):
        try:
            from urllib.request import Request, urlopen
        except ImportError:
            from urllib.request import Request, urlopen
        req = Request(url, data=json.dumps(body).encode(), headers=headers, method='POST')
        try:
            resp = urlopen(req, timeout=30)
        except Exception as e:
            msg = str(e)
            if hasattr(e, 'read'):
                msg += ' | ' + e.read().decode('utf-8', errors='replace')[:300]
            return {'status': 502, 'error': msg}

        if resp.status != 200:
            return {'status': resp.status, 'error': resp.read().decode('utf-8', errors='replace')[:300]}

        return self._parse_ndjson(resp)

    # ═══════════════════════════════════════
    #  解析 NDJSON 流 → 提取 PCM → 转 WAV
    # ═══════════════════════════════════════
    def _parse_ndjson(self, response):
        all_pcm = []
        buf = ''

        # 流式读取（分块）
        for chunk in self._iter_chunks(response):
            buf += chunk.decode('utf-8', errors='replace')
            lines = buf.split('\n')
            buf = lines.pop()  # 保留不完整的最后一行

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    code = obj.get('code', -1)

                    if code == 0 and 'data' in obj:
                        # base64 PCM → bytes
                        pcm = base64.b64decode(obj['data'])
                        all_pcm.append(pcm)

                    if code > 0 and code != 20000000:
                        msg = obj.get('message', f'错误码 {code}')
                        return {'status': 502, 'error': msg}

                except (json.JSONDecodeError, base64.binascii.Error):
                    continue

        if not all_pcm:
            return {'status': 502, 'error': '未收到音频数据，请检查 API Key 是否正确'}

        # 合并 PCM
        merged = b''.join(all_pcm)

        # PCM → WAV
        return self._pcm_to_wav(merged, 24000, 1, 16)

    def _iter_chunks(self, response):
        """跨库兼容的 chunk 迭代器"""
        if hasattr(response, 'iter_bytes'):
            yield from response.iter_bytes()
        elif hasattr(response, 'iter_content'):
            yield from response.iter_content(chunk_size=4096)
        else:
            yield response.read()

    # ═══════════════════════════════════════
    #  PCM → WAV 转换
    # ═══════════════════════════════════════
    @staticmethod
    def _pcm_to_wav(pcm, sample_rate, channels, bits):
        byte_rate = sample_rate * channels * (bits // 8)
        block_align = channels * (bits // 8)

        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + len(pcm),
            b'WAVE',
            b'fmt ',
            16,           # chunk size
            1,            # PCM = 1
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits,
            b'data',
            len(pcm),
        )
        return header + pcm

    # ═══════════════════════════════════════
    #  工具方法
    # ═══════════════════════════════════════
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')

    def _err(self, code, msg):
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({'error': msg}, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        pass

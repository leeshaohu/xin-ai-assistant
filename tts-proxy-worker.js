/**
 * 心语 AI - 豆包 TTS 代理
 * 部署到 Cloudflare Workers，解决浏览器 CORS 问题
 *
 * 用法：POST /  { apiKey, voice, text }
 * 返回：WAV 音频 (audio/wav)
 *
 * 部署步骤：
 * 1. 注册 https://dash.cloudflare.com → Workers & Pages → Create
 * 2. 把这段代码粘贴进去
 * 3. 部署后得到一个 https://xxx.workers.dev 的地址
 * 4. 把地址填到 chat.html 设置里的「代理URL」
 */

export default {
  async fetch(request) {
    // 只允许 POST
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    // CORS 预检
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    try {
      const body = await request.json();
      const { apiKey, voice, text } = body;

      if (!apiKey || !text) {
        return Response.json({ error: '缺少 apiKey 或 text' }, {
          status: 400,
          headers: { 'Access-Control-Allow-Origin': '*' },
        });
      }

      // 构造火山引擎 API v3 请求体（完全对齐 Talkify SeedTts2Engine）
      const volcBody = {
        user: { uid: 'xinyu_user_' + Date.now() },
        req_params: {
          text: text,
          speaker: voice || 'zh_female_vv_uranus_bigtts',
          audio_params: {
            format: 'pcm',
            sample_rate: 24000,
            speech_rate: 0,
            loudness_rate: 0,
          },
          additions: JSON.stringify({
            explicit_language: 'zh',
            disable_markdown_filter: true,
          }),
        },
      };

      // 请求火山引擎
      const resp = await fetch(
        'https://openspeech.bytedance.com/api/v3/tts/unidirectional',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': apiKey,
            'X-Api-Resource-Id': 'seed-tts-2.0',
            Connection: 'keep-alive',
          },
          body: JSON.stringify(volcBody),
        }
      );

      if (!resp.ok) {
        const errText = await resp.text();
        return Response.json({
          error: `火山引擎错误 ${resp.status}: ${errText.substring(0, 300)}`,
        }, {
          status: resp.status,
          headers: { 'Access-Control-Allow-Origin': '*' },
        });
      }

      // 解析 NDJSON 流式响应
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      const allPcmChunks = [];
      let buf = '';
      let hasError = false;
      let errorMsg = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop(); // 保留不完整的最后一段

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          try {
            const json = JSON.parse(trimmed);
            const code = json.code;

            // 音频数据块 (Base64 PCM)
            if (code === 0 && json.data) {
              const binaryStr = atob(json.data);
              const bytes = new Uint8Array(binaryStr.length);
              for (let j = 0; j < binaryStr.length; j++) {
                bytes[j] = binaryStr.charCodeAt(j);
              }
              allPcmChunks.push(bytes);
            }

            // 错误响应
            if (code > 0 && code !== 20000000) {
              errorMsg = json.message || `错误码 ${code}`;
              hasError = true;
            }
          } catch (e) {
            // 忽略解析失败的行
          }
        }

        if (hasError) break;
      }

      if (hasError) {
        return Response.json({ error: errorMsg }, {
          status: 502,
          headers: { 'Access-Control-Allow-Origin': '*' },
        });
      }

      if (allPcmChunks.length === 0) {
        return Response.json({ error: '未收到音频数据' }, {
          status: 502,
          headers: { 'Access-Control-Allow-Origin': '*' },
        });
      }

      // 合并 PCM 并转 WAV
      const totalLen = allPcmChunks.reduce((sum, c) => sum + c.length, 0);
      const merged = new Uint8Array(totalLen);
      let offset = 0;
      for (const chunk of allPcmChunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      const wavBuffer = pcmToWav(merged, 24000, 1, 16);

      return new Response(wavBuffer, {
        status: 200,
        headers: {
          'Content-Type': 'audio/wav',
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Expose-Headers': 'Content-Length',
          'Content-Length': String(wavBuffer.byteLength),
        },
      });
    } catch (err) {
      return Response.json({ error: '代理内部错误: ' + err.message }, {
        status: 500,
        headers: { 'Access-Control-Allow-Origin': '*' },
      });
    }
  },
};

// PCM 转 WAV (与 chat.html 中的实现一致)
function pcmToWav(pcmData, sampleRate, numChannels, bitsPerSample) {
  sampleRate = sampleRate || 24000;
  numChannels = numChannels || 1;
  bitsPerSample = bitsPerSample || 16;
  const dataLength = pcmData.length;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeString(view, 8, 'WAVE');

  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * (bitsPerSample / 8), true);
  view.setUint16(32, (numChannels * bitsPerSample) / 8, true);
  view.setUint16(34, bitsPerSample, true);

  writeString(view, 36, 'data');
  view.setUint32(40, dataLength, true);

  new Uint8Array(buffer).set(pcmData, 44);
  return buffer;
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

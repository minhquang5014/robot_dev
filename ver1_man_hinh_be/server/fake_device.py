# -*- coding: utf-8 -*-
"""Thiet bi gia: noi dung giao thuc xiaozhi de thu server ma khong can ESP32.

Gui mot cau tieng Viet duoi dang Opus 60ms roi im lang, xem server co tu phat
hien dut cau, tra loi, va gui Opus nguoc lai khong. Cau tra loi duoc giai ma
ra server/out/device_heard.wav de nghe lai.

    python server/xiaozhi_server.py --port 8000     # cua so 1
    python server/fake_device.py                    # cua so 2

Tep hoi mac dinh la server/out/hoi.mp3. Tu tao mot cau khac:
    python server/fake_device.py http://127.0.0.1:8000 duong/dan/cau-hoi.mp3
"""
import io, os, sys, json, time, asyncio, wave
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                              line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import av
import audio as A

HOST = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
SRC = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out', 'hoi.mp3')
SC = os.path.join(HERE, 'out')


def mp3_to_pcm(path):
    c = av.open(path)
    rs = av.audio.resampler.AudioResampler(format='s16', layout='mono', rate=A.SAMPLE_RATE)
    out = []
    for fr in c.decode(audio=0):
        for g in rs.resample(fr):
            out.append(g.to_ndarray().reshape(-1))
    return np.concatenate(out)


async def main():
    import aiohttp
    pcm = mp3_to_pcm(SRC)
    print('câu hỏi: %s  (%.2f giây)' % (os.path.basename(SRC), len(pcm)/A.SAMPLE_RATE))

    enc = A.OpusEncoder()
    dec = A.OpusDecoder()
    ws_url = HOST.replace('http', 'ws') + '/xiaozhi/v1/'

    async with aiohttp.ClientSession() as cs:
        async with cs.ws_connect(ws_url, headers={
                'Authorization': 'Bearer test', 'Protocol-Version': '1',
                'Device-Id': 'AA:BB:CC:DD:EE:FF', 'Client-Id': 'fake'}) as ws:
            await ws.send_json({'type': 'hello', 'version': 1, 'transport': 'websocket',
                                'audio_params': {'format': 'opus', 'sample_rate': 16000,
                                                 'channels': 1, 'frame_duration': 60}})
            m = await asyncio.wait_for(ws.receive_json(), 10)
            print('<< hello  session=%s' % m.get('session_id'))

            await ws.send_json({'type': 'listen', 'state': 'start', 'mode': 'auto'})
            t0 = time.monotonic()

            # Gui cau noi + 1.2 giay im lang de VAD chot
            tail = np.zeros(int(A.SAMPLE_RATE*1.2), np.int16)
            allpcm = np.concatenate([pcm, tail])
            sent = 0
            for i in range(0, len(allpcm)-A.FRAME_SAMPLES+1, A.FRAME_SAMPLES):
                for p in enc.encode(allpcm[i:i+A.FRAME_SAMPLES]):
                    await ws.send_bytes(p); sent += 1
                await asyncio.sleep(0.06)      # gui dung nhip thuc
            print('>> đã gửi %d gói Opus, im lặng 1.2s ở cuối' % sent)

            got = []; marks = {}
            try:
                while True:
                    msg = await asyncio.wait_for(ws.receive(), 25)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        d = json.loads(msg.data)
                        ms = (time.monotonic()-t0)*1000
                        k = d.get('type')
                        if k == 'llm':
                            marks['cảm xúc'] = ms; print('<< [%6.0f ms] llm emotion=%s' % (ms, d.get('emotion')))
                        elif k == 'stt':
                            marks['stt'] = ms; print('<< [%6.0f ms] stt   %r' % (ms, d.get('text')))
                        elif k == 'tts':
                            st = d.get('state')
                            if st == 'sentence_start':
                                print('<< [%6.0f ms] nói  %r' % (ms, d.get('text')))
                            elif st == 'start':
                                marks['tts start'] = ms
                            elif st == 'stop':
                                print('<< [%6.0f ms] tts stop' % ms); break
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        if 'tiếng đầu' not in marks:
                            marks['tiếng đầu'] = (time.monotonic()-t0)*1000
                            print('<< [%6.0f ms] gói Opus đầu tiên (%d byte)'
                                  % (marks['tiếng đầu'], len(msg.data)))
                        got.append(msg.data)
                    else:
                        break
            except asyncio.TimeoutError:
                print('HẾT GIỜ CHỜ')

    print('')
    print('nhận %d gói Opus' % len(got))
    if got:
        out = [dec.decode(p) for p in got]
        back = np.concatenate([o for o in out if len(o)])
        p = os.path.join(SC, 'device_heard.wav')
        A.write_wav(back, p)
        print('giải mã được %.2f giây tiếng -> %s' % (len(back)/A.SAMPLE_RATE, p))
    for k in ('cảm xúc', 'stt', 'tts start', 'tiếng đầu'):
        if k in marks:
            print('  %-10s %6.0f ms' % (k, marks[k]))

asyncio.run(main())

# server — đường ống voice → voice

Bộ não của robot. Nhận giọng nói, trả về giọng nói kèm một nhãn cảm xúc cho
firmware vẽ mặt.

```
audio vào ──> Groq Whisper ──> Groq LLM ──> EdgeTTS ──> audio ra
                (STT)          (+ cảm xúc)    (TTS)
```

Tách rời khỏi phần mạng có chủ đích: `pipeline.py` không biết gì về WebSocket
hay ESP32. Khi dựng server thật, nó gọi lại đúng ba hàm này, không phải viết lại.

| File | Việc |
|---|---|
| `pipeline.py` | `speech_to_text` → `think` → `text_to_speech`. Phần dùng lại được. Server async dùng `run_turn_stream` |
| `test_voice.py` | CLI chạy thử, đo thời gian từng chặng |
| `xiaozhi_server.py` | Server nói giao thức xiaozhi để ESP32 gọi vào. **Mốc 0**: mới bắt tay + ghi log, chưa nối AI |
| `.env.example` | Mẫu khai báo khoá. Copy thành `.env` — file đó **không** lên git |

## Chạy

```bash
pip install -r server/requirements.txt
cp server/.env.example server/.env        # rồi dán GROQ_API_KEY vào

python server/test_voice.py --text "Chào cậu"   # nhanh nhất, bỏ qua STT
python server/test_voice.py --record 4          # thu từ micro máy tính
python server/test_voice.py --chat              # nói liên tục, có nhớ ngữ cảnh
python server/test_voice.py --models            # xem Groq còn model nào

# Thêm --stream: TTS streaming, in thời điểm có TIẾNG ĐẦU TIÊN
python server/test_voice.py --in mic.wav --stream
# Thêm -v: in cả dòng quy đổi cảm xúc ([excited] -> happy)
```

Trong server async, dùng `run_turn_stream()` và bọc `contextlib.aclosing(...)`
để người dùng ngắt lời thì TTS dừng ngay:

```python
turn = pipeline.Turn()
async with contextlib.aclosing(pipeline.run_turn_stream(turn, audio_path=wav)) as g:
    async for mp3_chunk in g:
        ...   # turn.emotion đã có trước chunk đầu -> gửi cảm xúc trước
```

### Server giao thức xiaozhi (Mốc 0)

```bash
python server/xiaozhi_server.py --port 8000    # mặc định chỉ nghe 127.0.0.1
```

Mỗi lượt nghe, các gói Opus ESP32 gửi lên được lưu vào `server/out/ws_sessions/*.opuspkt`
(mỗi gói: 2 byte độ dài little-endian + payload) để làm bước giải mã sau này.

Hiện đã kiểm bằng **thiết bị giả lập** gửi đúng chuỗi tin như firmware: OTA trả địa
chỉ WebSocket, bắt tay `hello`, `listen` start/stop, đếm và lưu gói. **Chưa có ESP32
thật nào gọi vào.**

> **Chạy server ở máy chủ từ xa (Oracle, VPS), không chạy trên máy công ty.** ESP32
> phải gọi được vào server, nghĩa là server phải nhận kết nối từ ngoài. Mở cổng hay
> dựng tunnel (cloudflared, ngrok…) trên máy do công ty quản lý là đi vòng tường lửa
> của họ — IT theo dõi đúng loại việc này. Trên máy cá nhân, để `--host 127.0.0.1`
> và thử bằng thiết bị giả lập là an toàn.

> **Địa chỉ công khai thì ai biết cũng gọi được**, và mỗi lượt tốn hạn mức Groq của
> bạn. `XZ_TOKEN` được gửi kèm trong header, nhưng chính endpoint OTA lại trả token
> đó cho bất kỳ ai hỏi — nên nó **không** phải cơ chế bảo vệ thật.

## Giao thức xiaozhi — đọc từ firmware 2.5.0

Ghi lại để khỏi phải đọc lại code. Đường dẫn tính từ `xiaozhi-esp32/main/`.

**Đổi server không cần nạp lại firmware.** Firmware đọc `ota_url` trong NVS (namespace
`wifi`) trước, trống mới dùng `CONFIG_OTA_URL` (`ota.cc:48-55`). Trang cấu hình WiFi
`192.168.4.1`, tab nâng cao, ghi đúng khoá đó.

**Bước OTA** — `POST` kèm JSON thông tin thiết bị (`ota.cc:95-100`). Phản hồi:

| Trường | Tác dụng |
|---|---|
| `websocket: {url, token}` | Có trường này và **không** có `mqtt` thì firmware dùng WebSocket (`application.cc:538-545`) |
| `activation` | Không trả thì firmware **bỏ qua bước kích hoạt** |
| `firmware: {version, url}` | Không trả thì không nâng cấp |
| `server_time: {timestamp, timezone_offset}` | Đặt giờ hệ thống; offset tính bằng phút |

**WebSocket** (`protocols/websocket_protocol.cc`)

- Header: `Authorization: Bearer <token>`, `Protocol-Version: 1`, `Device-Id` (MAC), `Client-Id`.
- Thiết bị gửi `hello` (Opus, 16 kHz, mono, khung **60 ms**), rồi **chờ `hello` của server
  tối đa 10 giây**. `hello` của server bắt buộc có `transport: "websocket"`; `audio_params`
  quyết định tần số của audio server gửi xuống.
- Protocol-Version 1: gói binary là **Opus thô**, không có header.

**Thiết bị gửi lên** (`protocols/protocol.cc`): `listen` với `state` `start`/`stop`/`detect`,
`abort`, `mcp`. Mọi tin đều kèm `session_id` lấy từ `hello` của server.

**Bấm nút BOOT thì nghe ở chế độ `auto`** (`application.cc:807`, `:1189` — không có AEC
thì mặc định `AutoStop`). Thiết bị cứ gửi audio mãi, **server phải tự phát hiện người
nói đã dừng** (VAD) rồi mới trả lời. Chế độ `manual` chỉ dùng cho nút giữ-để-nói GPIO5.

**Server gửi xuống** (`application.cc:586-704`):

| Tin | Tác dụng trên thiết bị |
|---|---|
| `{"type":"stt","text":…}` | Hiện câu người dùng nói |
| `{"type":"llm","emotion":…}` | Đổi biểu cảm |
| `{"type":"tts","state":"start"}` | Chuyển sang trạng thái đang nói |
| `{"type":"tts","state":"sentence_start","text":…}` | Hiện câu robot đang nói |
| `{"type":"tts","state":"stop"}` | Chế độ `auto` thì quay lại nghe tiếp |
| binary | Opus theo `audio_params` trong `hello` của server |

## Kết quả đo — 17/09/2026

### Chọn model: nhỏ nhất không phải nhanh nhất

Prompt đã sửa (lỗi 6–8 bên dưới), 5 câu × 2 vòng = 10 lượt mỗi model. Chạy xen
kẽ giữa các model, để lúc Groq chậm thì model nào cũng chịu như nhau.

| Model | Trung vị | Dao động | Tag hợp lệ | Tiếng Việt có dấu |
|---|---|---|---|---|
| `qwen/qwen3.8-27b` | **362 ms** | 347–466 | 9/10 | 9/10 |
| `openai/gpt-oss-120b` | 547 ms | 395–882 | 10/10 | 10/10 |
| `openai/gpt-oss-20b` | 677 ms | 392–822 | 10/10 | 10/10 |
| `groq/compound-mini` | 1369 ms | 918–1625 | 10/10 | 10/10 |
| `allam-2-7b` | 419 ms | 351–991 | 9/10 | có dấu nhưng **nát** |

**Giữ `qwen`**: nhanh nhất, biên độ hẹp nhất. Lượt hỏng duy nhất của nó là trả lời
tiếng Anh (lỗi 8). `allam-2-7b` là model nhỏ nhất nhưng **không nhanh hơn**, và
tiếng Việt vô dụng: "Xin chào Mỹ, ấy là Mỹ!", xưng tôi/bạn, câu dài lan man, còn
dính 429. Trên Groq tốc độ phụ thuộc phần cứng phục vụ, không phụ thuộc kích cỡ.

Cùng model `qwen` mà hôm 16/09 đo 762 / 1337 ms, hôm nay 362 ms — free tier dao
động theo ngày, đừng tin một lần đo.

LLM giờ chỉ còn ~350 ms. **Đổi model không cứu được độ trễ nữa.**

### TTS streaming

Cùng một câu chạy xen kẽ hai chế độ, 4 vòng mỗi độ dài. Số là trung vị:

| Độ dài câu | Chờ cả file | Streaming: tiếng đầu | Streaming: xong câu |
|---|---|---|---|
| 10 ký tự | 616 ms | 461 ms | 624 ms |
| 66 ký tự | 698 ms | 494 ms | 732 ms |
| 79 ký tự | 634 ms | 436 ms | 676 ms |
| 103 ký tự | 712 ms | 446 ms | 672 ms |

- Streaming chỉ lợi **~200 ms ở trung vị** — ít hơn kỳ vọng, vì chờ cả file cũng
  chỉ ~0,7 s và **gần như không phụ thuộc độ dài câu**. Lần đo 1,8–2,1 s trước đó
  trong ngày là do mạng chậm, không phải do chờ file.
- Trong 16 lần, tiếng đầu của streaming chưa lần nào quá 551 ms; chờ cả file có
  2 lần vọt 2,2 s và 4,2 s. Mẫu còn nhỏ, chưa đủ khẳng định streaming chống được
  đuôi dài.

### Trọn vòng qua CLI, có streaming

6 lượt `--stream` (4 từ file ghi âm mic INMP441 thật của robot, 2 lượt `--text`):
tiếng đầu tiên **1,5–2,9 s, trung vị ~1,9 s — chưa lọt ngân sách 1,5 s.**

3 lượt đầu từ file mic: STT 558–807 ms, LLM 319–478 ms, chunk TTS đầu 930–1363 ms.
Chunk TTS đầu qua CLI chậm gấp đôi so với đo trong một tiến trình (~450 ms). Khởi
động nguội — import `edge_tts` ~100 ms, lần gọi đầu chậm hơn ~100 ms — chỉ giải
thích được một phần; phần còn lại chưa tái hiện được, nhiều khả năng là mạng.

STT giờ là chặng lớn nhất còn cắt được (xem Việc tiếp theo).

## Kết quả đo — 16/09/2026

*Số liệu cũ. So sánh model đã đo lại ở trên. Nhận định bên dưới rằng streaming sẽ
làm "cảm giác trễ giảm mạnh" chưa đúng — đo thật ngày 17/09 chỉ lợi ~200 ms.*

Khép kín được vòng voice → voice. Chặng STT kiểm bằng cách lấy chính file MP3
do TTS sinh ra làm đầu vào, nhận dạng lại đúng nguyên văn, đủ dấu.

| Chặng | Độ trễ | Ghi chú |
|---|---|---|
| STT | 507 ms | `whisper-large-v3-turbo`, ép `language=vi` |
| LLM | trung vị **1898 ms** | dao động rất mạnh: 678 – 3274 ms |
| TTS | 778 ms | khi chạy trót lọt. Trúng đợt hỏng thì ~8 giây |

**Tổng thực tế 3–4 giây**, vượt xa ngân sách 1,5 giây đặt ra ở README gốc.
Không phải do code sai mà do bản chất: ba lần gọi mạng nối tiếp, mỗi lần đều có
đuôi dao động dài. Đây là lý do phải chuyển sang **TTS streaming** — robot bắt
đầu phát tiếng khi mới nhận được chunk đầu, thay vì đợi trọn câu. Tổng thời gian
không đổi nhưng cảm giác trễ giảm mạnh.

### So sánh model LLM

`llama-3.1-8b-instant` mà README gốc đề xuất **đã bị Groq gỡ bỏ**. Đo lại các
model còn sống (trung vị 3 lần, prompt tiếng Việt có dấu):

| Model | Trung vị | Nhận xét |
|---|---|---|
| `qwen/qwen3.8-27b` | 762 / 1337 ms | **Đang dùng.** Không đốt token reasoning |
| `openai/gpt-oss-120b` | 723 ms | Nhanh hơn chút, nhưng token suy nghĩ ăn vào hạn mức |
| `openai/gpt-oss-20b` | 809 ms | Hay chèn tag `[...]` thừa giữa câu |
| `groq/compound-mini` | 1171 ms | Chậm nhất |

Hai con số ở cột `qwen` là hai lần đo khác buổi (3 lượt và 6 lượt). Chênh lệch
đó cho thấy đo một lần rồi tin là không đủ — free tier đổi theo giờ.

Chọn `qwen` làm mặc định vì nó **không sinh token reasoning**, nên mỗi lượt tốn
ít hạn mức hơn, mà trần 8000 token/phút mới là chỗ siết thật chứ không phải
1000 request/ngày.

Kiểm 6 lượt liên tiếp: **6/6 tag cảm xúc hợp lệ** và chọn đúng ngữ cảnh
(`[delicious]` cho món ăn, `[funny]` cho chuyện cười, `[sad]` cho lúc chia tay),
**6/6 câu có dấu đầy đủ**, tất cả đều trong 2 câu. Biên độ dao động 315–1380 ms,
**hẹp hơn hẳn** `gpt-oss-120b` (678–3274 ms) — với robot thì ổn định đáng giá
hơn nhanh.

Chạy `--models` trước khi tin bảng này — Groq gỡ model theo thời gian.

## Lỗi đã gặp và cách sửa

**1. Prompt viết không dấu thì model trả lời cũng không dấu.**
Đây là lỗi nguy hiểm nhất vì nó âm thầm. Prompt ban đầu viết
`Xung "to", goi nguoi doi dien la "cau"`, model bắt chước y hệt văn phong đó:

```
trước:  [happy] To vui lắm! Cau muốn làm gì hôm nay?
sau :   [happy] Tớ vui lắm! Cậu muốn làm gì hôm nay?
```

EdgeTTS đọc "To"/"Cau" thành từ khác hẳn "Tớ"/"Cậu". Robot sẽ nói một thứ tiếng
Việt lơ lớ mà rất khó lần ra nguyên nhân. `SYSTEM_PROMPT` nay viết có dấu đầy đủ
và có hẳn một luật bắt buộc model viết có dấu.

**2. `gpt-oss` là model reasoning — nó nuốt sạch `max_tokens`.**
(Không còn là mặc định, nhưng giữ ghi chú vì rất dễ vấp lại khi đổi model.)
Với `max_tokens: 150`, 148 token bị đốt vào phần suy nghĩ nội bộ, `content` trả
về **chuỗi rỗng**, `finish_reason: length`. Token reasoning tính chung hạn mức
chứ không tách riêng. Sửa: `max_tokens: 400` và `reasoning_effort: low`
(723 ms so với 1927 ms khi để mặc định).

**3. Console Windows là cp1252.** In tiếng Việt có dấu là `UnicodeEncodeError`
ngay giữa lúc chạy. `test_voice.py` ép UTF-8 cho stdout/stderr trước khi làm gì
khác.

**4. Model nhỏ chèn tag thừa giữa câu.** `gpt-oss-20b` trả về
`... cậu sao rồi? [laughing] Tớ đang chờ kẹo`. Không lọc thì TTS đọc to chữ
"laughing" ra loa. `_strip_stray_tags()` quét sạch mọi `[...]` còn sót.

**5. EdgeTTS hỏng 31%.** Xem mục dưới.

**6. Model bịa tên cảm xúc.** 1/4 câu chào trả `[excited]` — không có trong danh
sách firmware hiểu. Trước đây nó âm thầm về `neutral`, nhìn kết quả không phân
biệt được với lúc model chủ động chọn neutral. Sửa: `EMOTION_ALIASES` quy tên gần
nghĩa (`excited` → `happy`…), log WARNING cho tag lạ và câu quên tag,
`Turn.emotion_raw` giữ tag nguyên văn.

**7. Model chép nguyên câu ví dụ.** 2/4 câu chào trả đúng từng chữ câu mẫu trong
prompt, `Tớ đây! Cậu vừa đi đâu về thế?` — về nhà lần nào robot cũng chào y một
câu. Nguyên nhân: câu ví dụ trùng đúng tình huống hay gặp nhất. Sửa: đổi ví dụ
sang tình huống ít gặp, thêm luật "ví dụ chỉ minh hoạ định dạng". Đo lại:
**0/50 lần chép** trên cả 5 model.

**8. `qwen` thỉnh thoảng trả lời tiếng Anh.** `[d] Oh my, that sounds delicious!`
— 1/10 lượt, hỏng cả tag. Giọng tiếng Việt đọc câu tiếng Anh nghe rất tệ. Sửa:
thêm "không dùng tiếng Anh" vào prompt, và `think()` hỏi lại 1 lần nếu câu trả lời
không có chữ tiếng Việt nào — chỉ tốn thêm ~360 ms ở đúng lượt hỏng, lịch sử hội
thoại chỉ lưu câu đúng. Nhánh hỏi lại đã kiểm bằng cách giả lập Groq trả tiếng Anh.

**9. `asyncio.run()` gọi từ server async là nổ.** `text_to_speech` cũ gọi
`asyncio.run()`, mà server WebSocket đã có event loop sẵn → `RuntimeError`. Sửa:
thêm API async `text_to_speech_stream()`, `text_to_speech_async()`,
`run_turn_stream()`. Bản đồng bộ giữ cho CLI, bị gọi nhầm trong event loop thì báo
lỗi rõ ràng. STT và LLM dùng `requests` (chặn) nên được đẩy sang thread.

**Không phải lỗi: `Unclosed client session` khi thử ngắt lời.** Script dừng stream
giữa chừng rồi thoát ngay thì hiện cảnh báo này, rất dễ tưởng là rò kết nối.
Kiểm lại cả bản trước và sau khi sửa: server chạy liên tục thì Python tự dọn,
**0 cảnh báo** ở cả hai. Cảnh báo chỉ hiện khi tiến trình thoát ngay sau lúc ngắt.
`text_to_speech_stream` vẫn đóng websocket tường minh trong `finally` để việc đóng
xảy ra đúng lúc ngắt, nhưng đó là dọn dẹp cho gọn, không phải vá lỗi rò.

## Hạn chế đã biết

**EdgeTTS trả về `NoAudioReceived` khoảng 31% số lần gọi.** Đo 48 lần: hỏng 15.
Đã loại trừ hai giả thuyết — **không** liên quan độ dài câu, **không** liên quan
tham số `pitch`/`rate`. Nó hỏng **theo từng đợt**: có lúc 5/6 lần liên tiếp hỏng
rồi tự nhiên tốt lại.

Vì hỏng theo đợt nên thử lại liên tiếp là vô ích — `text_to_speech()` retry 4
lần với backoff giãn dần. Nhưng khi trúng đợt xấu thì mất ~8 giây thay vì 778 ms.

Ngày 17/09/2026, hơn 50 lần gọi trên một mạng khác **không lần nào hỏng**. Khớp
với nhận định nó hỏng theo đợt chứ không đều. Streaming chỉ thử lại được khi
**chưa** phát ra chunk nào; đứt giữa câu thì báo lỗi luôn, vì đọc lại từ đầu sẽ
lặp đoạn đã phát.

Về lâu dài nên **cache sẵn các câu hay dùng** (chào hỏi, "tớ không biết", câu
đệm) để đợt hỏng không đụng tới chúng, và chuẩn bị một nhà cung cấp TTS dự phòng.
Đây là cái giá của endpoint miễn phí không chính thức.

**Hạn mức Groq siết ở token chứ không phải request.** Header báo 1000
request/ngày nhưng chỉ **8000 token/phút**. Mỗi lượt tốn ~700 token, tức trần
khoảng 11 lượt/phút. Robot để bàn thì thoải mái, nhưng đừng benchmark bằng vòng
lặp.

**Độ trễ Groq free tier dao động mạnh** — 678 đến 3274 ms cho cùng loại request.
Không phải do rate limit (đo lúc còn 986/1000 request, `queue_time` 0,31 s).
Đó là đặc tính của free tier, phải thiết kế chấp nhận nó.

## Chưa kiểm chứng

- Chưa chạy `--record` / `--chat` với micro máy tính. Hai đường đó cần người nói.
  Đường `--in` thì đã chạy với file ghi âm từ mic INMP441 thật của robot.
- Chưa đo với giọng `vi-VN-NamMinhNeural`, mới thử `HoaiMyNeural`.
- Số liệu độ trễ đo từ Việt Nam, hai buổi, và hai buổi lệch nhau gấp đôi.
- **Chưa phát streaming thật.** Trên Mac mới đo thời gian rồi phát file sau khi xong.
  Phát từng chunk là việc của ESP32 qua Opus, chưa làm.
- Chưa đo được tỷ lệ trả lời tiếng Anh sau khi sửa prompt — tỷ lệ gốc 1/10 cần
  nhiều mẫu mới thấy khác biệt.
- **`xiaozhi_server.py` chưa được ESP32 thật gọi vào.** Bảng giao thức ở trên đọc từ
  code firmware, còn server mới chỉ test bằng thiết bị giả lập. Chưa thử ESP32
  (không PSRAM) bắt tay TLS với tên miền công khai khác `api.tenclass.net`.

## Việc tiếp theo

1. **Mốc 0** — code xong (`xiaozhi_server.py`), đã qua thiết bị giả lập. Còn lại:
   dựng trên máy chủ từ xa, đổi `ota_url` của ESP32 sang đó, xem log bắt tay thật.
2. **Opus + VAD** ở server. Đã xác nhận trong firmware: bấm BOOT là chế độ `auto`,
   thiết bị không tự cắt lượt, server phải làm.
3. **Nối `pipeline.py` vào** — phần này xong rồi, chỉ là gọi hàm.
4. **TTS streaming** — phía pipeline xong (`run_turn_stream`). Còn lại: đổi chunk
   MP3 sang Opus cho ESP32.
5. **Cắt độ trễ STT** — chặng lớn nhất còn cắt được, 560–810 ms với file WAV 5 giây.
   Hai hướng chưa thử: gửi thẳng Opus từ thiết bị (nhỏ hơn WAV nhiều lần) và cắt
   khoảng lặng trước khi upload.
6. **Đôi mắt trên OLED** — làm sau cùng vì lúc đó mới biết server gửi cảm xúc nào.

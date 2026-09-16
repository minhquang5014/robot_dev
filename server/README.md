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
| `pipeline.py` | `speech_to_text` → `think` → `text_to_speech`. Phần dùng lại được |
| `test_voice.py` | CLI chạy thử, đo thời gian từng chặng |
| `.env.example` | Mẫu khai báo khoá. Copy thành `.env` — file đó **không** lên git |

## Chạy

```bash
pip install -r server/requirements.txt
cp server/.env.example server/.env        # rồi dán GROQ_API_KEY vào

python server/test_voice.py --text "Chào cậu"   # nhanh nhất, bỏ qua STT
python server/test_voice.py --record 4          # thu từ micro máy tính
python server/test_voice.py --chat              # nói liên tục, có nhớ ngữ cảnh
python server/test_voice.py --models            # xem Groq còn model nào
```

## Kết quả đo — 16/09/2026

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

## Hạn chế đã biết

**EdgeTTS trả về `NoAudioReceived` khoảng 31% số lần gọi.** Đo 48 lần: hỏng 15.
Đã loại trừ hai giả thuyết — **không** liên quan độ dài câu, **không** liên quan
tham số `pitch`/`rate`. Nó hỏng **theo từng đợt**: có lúc 5/6 lần liên tiếp hỏng
rồi tự nhiên tốt lại.

Vì hỏng theo đợt nên thử lại liên tiếp là vô ích — `text_to_speech()` retry 4
lần với backoff giãn dần. Nhưng khi trúng đợt xấu thì mất ~8 giây thay vì 778 ms.

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

- Chưa chạy `--record` / `--chat` với micro thật. Hai đường đó cần người nói.
- Chưa đo với giọng `vi-VN-NamMinhNeural`, mới thử `HoaiMyNeural`.
- Số liệu độ trễ đo từ Việt Nam, một buổi. Chưa biết đổi theo giờ thế nào.

## Việc tiếp theo

1. **Mốc 0** — endpoint `①` trả JSON tĩnh + WebSocket server rỗng, chứng minh
   ESP32 bắt tay được. Chưa nối AI vào.
2. **Opus + VAD** ở server. Thiết bị không có VAD, server phải tự cắt lượt.
3. **Nối `pipeline.py` vào** — phần này xong rồi, chỉ là gọi hàm.
4. **TTS streaming**, theo số liệu ở trên.
5. **Đôi mắt trên OLED** — làm sau cùng vì lúc đó mới biết server gửi cảm xúc nào.

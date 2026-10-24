/*
  Test mic INMP441 + amp MAX98357A theo ĐÚNG chân mà xiaozhi dùng
  (board bread-compact-esp32). Muc dich: kiem tra phan cung truoc khi
  quy ket loi cho firmware.

  Chan:
    Mic INMP441:  SCK=26  WS=25  SD=32
    Amp MAX98357A: BCLK=14  LRC=27  DIN=33

  Chuong trinh lam 2 viec xen ke:
    1. Moi 5 giay phat 1 tieng bip 1kHz  -> nghe thay = loa + amp OK
    2. Con lai: doc mic, in muc am thanh -> so nhay len khi vo tay = mic OK
*/
#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

#define MIC_SCK 26
#define MIC_WS  25
#define MIC_SD  32
#define SPK_BCLK 14
#define SPK_LRC  27
#define SPK_DIN  33

#define SR         16000
#define BUF_LEN    512
#define MIC_GAIN   4

static int32_t rawBuf[BUF_LEN];
static int16_t outBuf[BUF_LEN];

void setupMic() {
  i2s_config_t c = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SR,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4, .dma_buf_len = BUF_LEN, .use_apll = false,
  };
  i2s_pin_config_t p = { .mck_io_num = I2S_PIN_NO_CHANGE, .bck_io_num = MIC_SCK, .ws_io_num = MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE, .data_in_num = MIC_SD };
  if (i2s_driver_install(I2S_NUM_0, &c, 0, NULL) != ESP_OK) { Serial.println("LOI: I2S mic"); return; }
  i2s_set_pin(I2S_NUM_0, &p);
  Serial.println("Mic I2S: OK");
}

void setupSpk() {
  i2s_config_t c = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = SR,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4, .dma_buf_len = BUF_LEN, .use_apll = false,
    .tx_desc_auto_clear = true,
  };
  i2s_pin_config_t p = { .mck_io_num = I2S_PIN_NO_CHANGE, .bck_io_num = SPK_BCLK, .ws_io_num = SPK_LRC,
    .data_out_num = SPK_DIN, .data_in_num = I2S_PIN_NO_CHANGE };
  if (i2s_driver_install(I2S_NUM_1, &c, 0, NULL) != ESP_OK) { Serial.println("LOI: I2S loa"); return; }
  i2s_set_pin(I2S_NUM_1, &p);
  i2s_zero_dma_buffer(I2S_NUM_1);
  Serial.println("Loa I2S: OK");
}

void beep(int ms, int freq) {
  Serial.println(">>> BIP - ban phai NGHE THAY tieng nay");
  int total = SR * ms / 1000;
  size_t w;
  for (int done = 0; done < total; done += BUF_LEN) {
    for (int i = 0; i < BUF_LEN; i++)
      outBuf[i] = (int16_t)(6000.0 * sinf(2.0f * PI * freq * (done + i) / SR));
    i2s_write(I2S_NUM_1, outBuf, BUF_LEN * sizeof(int16_t), &w, portMAX_DELAY);
  }
  i2s_zero_dma_buffer(I2S_NUM_1);
}

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println("\n=== TEST PHAN CUNG AM THANH (chan xiaozhi) ===");
  setupMic();
  setupSpk();
  Serial.println("Vo tay hoac noi to -> so ben duoi phai nhay len.\n");
}

void loop() {
  static uint32_t lastBeep = 0;
  static uint8_t n = 0;

  if (millis() - lastBeep > 5000) { lastBeep = millis(); beep(400, 1000); }

  size_t br = 0;
  i2s_read(I2S_NUM_0, rawBuf, sizeof(rawBuf), &br, portMAX_DELAY);
  int ns = br / sizeof(int32_t);

  int32_t peak = 0;
  for (int i = 0; i < ns; i++) {
    int32_t s = rawBuf[i] >> 16;
    int32_t a = s < 0 ? -s : s;
    if (a > peak) peak = a;
    s *= MIC_GAIN;
    if (s > 32767) s = 32767;
    if (s < -32768) s = -32768;
    outBuf[i] = (int16_t)s;
  }

  if (++n >= 8) { n = 0; Serial.printf("muc mic: %ld\n", (long)peak); }

  size_t w = 0;
  i2s_write(I2S_NUM_1, outBuf, ns * sizeof(int16_t), &w, portMAX_DELAY);
}

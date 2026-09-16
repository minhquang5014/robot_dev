/*
  Ghi am tu INMP441 roi day PCM tho qua serial ve may tinh.
  Chan theo cau hinh xiaozhi: SCK=26  WS=25  SD=32

  Giao thuc: may tinh gui ky tu 'r' -> ESP32 tra ve
      "RECSTART" + (SR * 2 * so_giay) byte PCM 16-bit little-endian + "RECEND"
  Gui 's' -> tra ve mot dong muc am thanh hien tai (de ngam nghe truoc khi ghi).
*/
#include <Arduino.h>
#include <driver/i2s.h>

#define MIC_SCK   26
#define MIC_WS    25
#define MIC_SD    32
#define SR        16000
#define BUF_LEN   512
#define REC_SECS  5

static int32_t rawBuf[BUF_LEN];
static int16_t pcmBuf[BUF_LEN];

void setupMic() {
  i2s_config_t c = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SR,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = BUF_LEN,
    .use_apll = false,
  };
  i2s_pin_config_t p = {
    .mck_io_num = I2S_PIN_NO_CHANGE,
    .bck_io_num = MIC_SCK,
    .ws_io_num = MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = MIC_SD
  };
  i2s_driver_install(I2S_NUM_0, &c, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &p);
}

// doc 1 khung, tra ve so mau, dat PCM 16-bit vao pcmBuf
int readFrame(int32_t *peakOut) {
  size_t br = 0;
  i2s_read(I2S_NUM_0, rawBuf, sizeof(rawBuf), &br, portMAX_DELAY);
  int ns = br / sizeof(int32_t);
  int32_t peak = 0;
  for (int i = 0; i < ns; i++) {
    // INMP441 can trai 24-bit trong khung 32-bit -> >>16 ra int16 chuan.
    // Khong khuech dai o day: de may tinh tu chuan hoa, tranh xen ngon.
    int32_t s = rawBuf[i] >> 16;
    int32_t a = s < 0 ? -s : s;
    if (a > peak) peak = a;
    pcmBuf[i] = (int16_t)s;
  }
  if (peakOut) *peakOut = peak;
  return ns;
}

void setup() {
  Serial.begin(921600);
  delay(400);
  setupMic();
  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) { int32_t pk; readFrame(&pk); return; }

  char cmd = Serial.read();

  if (cmd == 's') {
    int32_t pk; readFrame(&pk);
    Serial.printf("LEVEL %ld\n", (long)pk);
    return;
  }

  if (cmd == 'r') {
    // bo vai khung dau cho DMA on dinh
    for (int i = 0; i < 6; i++) { int32_t pk; readFrame(&pk); }
    Serial.print("RECSTART");
    Serial.flush();
    long total = (long)SR * REC_SECS;
    long sent = 0;
    while (sent < total) {
      int ns = readFrame(NULL);
      if (sent + ns > total) ns = total - sent;
      Serial.write((uint8_t *)pcmBuf, ns * sizeof(int16_t));
      sent += ns;
    }
    Serial.flush();
    Serial.print("RECEND");
    Serial.flush();
  }
}

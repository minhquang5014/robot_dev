/*
  CHI THU LOA: MAX98357A + loa 4-8 ohm tren ESP32-S3 (ver1, bread-compact-s3-otto).
  Khong can mic, WiFi hay server — nghe thay la duong I2S -> amp -> loa con tot.

      MAX98357A DIN  -> GPIO7      BCLK -> GPIO15      LRC -> GPIO16
                VIN  -> 5V         GND  -> GND         GAIN -> GND (12 dB), SD de trong

  Lap lai moi ~6 giay, Serial (115200, cong usbmodem) bao dang phat gi:
      1. bip 1 kHz NHO (25%)      -> nghe duoc = loa song
      2. bip 1 kHz TO (90%)       -> so sanh do to; re/vo tieng = nguon yeu hoac loa qua tai
      3. quet 200 -> 4000 Hz      -> loa nho thuong yeu duoi ~300 Hz, do la binh thuong
      4. do-re-mi-fa-son          -> nghe co dut quang khong (dut = day I2S long / nguon sut)

  Gui mau STEREO giong nhau hai kenh: MAX98357A tron (L+R)/2 khi SD de trong, nen
  kenh nao cung ra loa.

  Nap: arduino-cli ... --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashSize=16M
  Xong thi nap lai firmware robot (idf.py flash).
*/
#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

#define SPK_DIN   7
#define SPK_BCLK  15
#define SPK_LRC   16
#define SR        16000

void setupSpeaker() {
  i2s_config_t c = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = SR,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = true,   // het du lieu thi phat im lang, khong lap lai rac
  };
  i2s_pin_config_t p = {
    .mck_io_num = I2S_PIN_NO_CHANGE,   // bo trong thi mac dinh GPIO0 -> mclk config failed
    .bck_io_num = SPK_BCLK,
    .ws_io_num = SPK_LRC,
    .data_out_num = SPK_DIN,
    .data_in_num = I2S_PIN_NO_CHANGE,
  };
  i2s_driver_install(I2S_NUM_0, &c, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &p);
}

// Phat mot doan sin (tan so co the doi dan tu f0 sang f1), bien do 0..1.
void tone2(float f0, float f1, int ms, float amp) {
  static int16_t buf[256 * 2];
  int total = SR * ms / 1000;
  float phase = 0;
  for (int i = 0; i < total; i += 256) {
    int n = min(256, total - i);
    for (int k = 0; k < n; k++) {
      float t = (float)(i + k) / total;
      float f = f0 + (f1 - f0) * t;
      // vao/ra 5 ms cho khoi bup bup
      float env = min(1.0f, min((i + k) / (SR * 0.005f), (total - i - k) / (SR * 0.005f)));
      int16_t s = (int16_t)(amp * env * 32767 * sinf(phase));
      phase += 2 * PI * f / SR;
      if (phase > 2 * PI) phase -= 2 * PI;
      buf[2 * k] = s;
      buf[2 * k + 1] = s;
    }
    size_t w;
    i2s_write(I2S_NUM_0, buf, n * 4, &w, portMAX_DELAY);
  }
}

void silence(int ms) { tone2(0, 0, ms, 0); }

void setup() {
  Serial.begin(115200);
  delay(300);
  setupSpeaker();
  Serial.println("\n### spk_test ###");
}

void loop() {
  Serial.println("1. bip 1 kHz NHO (25%)");
  tone2(1000, 1000, 500, 0.25);  silence(500);
  Serial.println("2. bip 1 kHz TO (90%)");
  tone2(1000, 1000, 500, 0.90);  silence(500);
  Serial.println("3. quet 200 -> 4000 Hz");
  tone2(200, 4000, 2000, 0.6);   silence(400);
  Serial.println("4. do-re-mi-fa-son");
  const float notes[] = {523, 587, 659, 698, 784};
  for (float f : notes) { tone2(f, f, 220, 0.6); silence(40); }
  silence(1500);
}

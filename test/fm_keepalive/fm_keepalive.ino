/*
  Test mach sac + tang ap FM5324GA voi ESP32 WROOM, CHAY BANG PIN, TU GHI LOG.

  ESP32 tu "nhan nut K" theo nhip, do duong 5V qua cau chia ap, va ghi moi thu
  vao FLASH (LittleFS) — khong phai RAM: RAM mat sach khi mat dien, ma luc can bat
  nhat chinh la luc mach FM tat lam ESP32 mat dien. Cam USB lai de lay log.

  DAU NOI

      Pin LiPo (+) -> B+     Pin LiPo (-) -> B-
      FM5324GA 5V  -> ESP32 chan 5V (VIN)
      FM5324GA GND -> ESP32 GND
      FM5324GA K   -> ESP32 GPIO18      (noi thang — K luc nghi chi ~0.8V)
                   Board ESP32-D0WD-V3 dang dung khong ra chan GPIO16/17 (TX2/RX2)
      5V -[10k]-+-[10k]- GND, diem giua -> GPIO34

  CACH TEST
      1. Nap sketch (co USB). Go `c` de xoa log cu neu muon.
      2. Rut USB. Mach FM phai dang bat (den ESP32 nhay) — neu tat thi cham K
         xuong GND mot cai.
      3. De chay 15-20 phut bang pin.
      4. Cam USB, go `d` de in log.

  MOI DONG LOG
      S<phien> <giay>s  V=<5V>  [su kien]
      phien = so lan ESP32 khoi dong (luu trong flash). Phien moi xuat hien giua
      chung = ESP32 da mat dien roi co lai — tuc mach FM da tat.
      Khong co dong ho that (khong mang) nen thoi gian tinh tu luc bat.

  DEN LED
      nhay 1 lan / giay = dang song,  nhay nhanh 3 lan = vua nhan K

  LENH SERIAL 115200
      d  in log      c  xoa log      p  nhan K ngay      a  bat/tat tu nhan K
*/
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_system.h>

#define PIN_K        18
#define PIN_SENSE    34     // ADC1, chi doc
#define PIN_LED      2

unsigned long KEEPALIVE_MS = 15000;   // 0 = khong nhan K — da thu 26/10: mach FM tu tat
const unsigned long PRESS_MS = 200;
const unsigned long LOG_MS   = 5000;  // ghi dien ap moi 5 giay
const bool LOAD_LIKE_ROBOT   = true;  // bat WiFi quet dinh ky -> ~100 mA nhu robot

const char* LOG = "/fmlog.txt";
uint32_t session = 0;
unsigned long lastPress = 0, lastBlink = 0, lastScan = 0, lastLog = 0;

float read5V() {
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(PIN_SENSE);   // trung binh 8 lan
  return mv / 8 * 2 / 1000.0;                                          // cau chia doi -> x2
}

// Ghi ngay va dong file moi dong: mat dien giua chung thi chi mat dong dang ghi.
void logLine(const char* event) {
  char line[96];
  snprintf(line, sizeof(line), "S%lu %7.1fs  V=%.2f  %s\n",
           (unsigned long)session, millis() / 1000.0, read5V(), event);
  File f = LittleFS.open(LOG, FILE_APPEND);
  if (f) { f.print(line); f.close(); }
  Serial.print(line);
}

void pressK() {
  digitalWrite(PIN_K, LOW);
  pinMode(PIN_K, OUTPUT_OPEN_DRAIN);   // chi keo xuong GND, khong bao gio day 3.3V vao K
  digitalWrite(PIN_K, LOW);
  delay(PRESS_MS);
  pinMode(PIN_K, INPUT);               // tha noi = nha nut
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_LED, HIGH); delay(60);
    digitalWrite(PIN_LED, LOW);  delay(60);
  }
}

const char* resetReason() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "bat nguon (mat dien roi co lai)";
    case ESP_RST_BROWNOUT: return "SUT AP (brownout)";
    case ESP_RST_SW:       return "reset phan mem";
    case ESP_RST_EXT:      return "reset ngoai / nut EN";
    case ESP_RST_PANIC:    return "loi chuong trinh";
    default:               return "khac";
  }
}

void dumpLog() {
  Serial.println("=== LOG BAT DAU ===");
  File f = LittleFS.open(LOG, FILE_READ);
  if (f) { while (f.available()) Serial.write(f.read()); f.close(); }
  Serial.println("=== LOG KET THUC ===");
}

void setup() {
  pinMode(PIN_K, INPUT);               // luc khoi dong: tha noi, khong "nhan nham"
  pinMode(PIN_LED, OUTPUT);
  Serial.begin(115200);
  delay(300);
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);

  LittleFS.begin(true);                // lan dau: tu format
  Preferences p;
  p.begin("fmtest", false);
  session = p.getUInt("session", 0) + 1;
  p.putUInt("session", session);
  p.end();

  char ev[64];
  snprintf(ev, sizeof(ev), "=== KHOI DONG: %s ===", resetReason());
  logLine(ev);

  if (LOAD_LIKE_ROBOT) WiFi.mode(WIFI_STA);
  lastPress = lastLog = millis();
}

void loop() {
  unsigned long now = millis();

  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'd') dumpLog();
    if (c == 'c') { LittleFS.remove(LOG); Serial.println(">> da xoa log"); }
    if (c == 'p') { pressK(); logLine("NHAN K (lenh tay)"); }
    if (c == 'a') {
      KEEPALIVE_MS = KEEPALIVE_MS ? 0 : 15000;
      lastPress = now;
      logLine(KEEPALIVE_MS ? "tu nhan K: BAT" : "tu nhan K: TAT");
    }
  }

  if (KEEPALIVE_MS && now - lastPress >= KEEPALIVE_MS) {
    lastPress = now;
    pressK();
    logLine("NHAN K");
  }

  if (now - lastLog >= LOG_MS) {
    lastLog = now;
    logLine("");
  }

  if (now - lastBlink >= 1000) {
    lastBlink = now;
    digitalWrite(PIN_LED, HIGH); delay(40); digitalWrite(PIN_LED, LOW);
  }

  if (LOAD_LIKE_ROBOT && now - lastScan >= 10000) {
    lastScan = now;
    WiFi.scanNetworks(true);
  }
}

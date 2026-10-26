/*
  Test mach sac + tang ap FM5324GA voi ESP32 WROOM: ESP32 "nhan nut K" theo
  nhip de mach khong tu tat tang ap.

  DAU NOI (chi 4 thu: pin, FM5324GA, ESP32, 1 day K)

      Pin LiPo (+) -> B+     Pin LiPo (-) -> B-
      FM5324GA 5V  -> ESP32 chan 5V (VIN)
      FM5324GA GND -> ESP32 GND
      FM5324GA K   -> ESP32 GPIO17      (noi thang — K luc nghi chi ~0.8V)
      (tuy chon) 5V -[10k]-+-[10k]- GND, diem giua -> GPIO34

  Bat lan dau: cham K xuong GND bang day mot cai (ESP32 chua co dien thi chua
  tu nhan duoc). Tu do ESP32 tu nhan K moi KEEPALIVE_MS.

  KHONG cam cap USB vao may tinh luc test bang pin: cong USB cung cap 5V, mach
  FM co tat thi ESP32 van song nho USB -> ket qua sai. Nhin DEN LED thay log:

      nhay 1 lan / giay         ESP32 dang song
      nhay nhanh 3 lan          vua "nhan K"
      den tat han               mach FM da tat 5V (hoac het pin)

  Hai che do, chon bang KEEPALIVE_MS:
      15000   ESP32 nhan K moi 15 giay — thu xem co giu duoc 5V khong
      0       KHONG nhan — thu xem rieng ESP32 lam tai thi mach co tu tat khong

  Cam USB vao (khong co pin) de xem Serial 115200: in moi lan nhan K va dien
  ap 5V neu co noi cau chia ap.
*/
#include <WiFi.h>

#define PIN_K        17     // noi thang chan K, open-drain
#define PIN_SENSE    34     // ADC1, chi doc — diem giua cau chia ap 10k/10k (tuy chon)
#define PIN_LED      2      // den co san tren hau het board ESP32 DevKit

const unsigned long KEEPALIVE_MS = 15000;   // 0 = khong nhan K
const unsigned long PRESS_MS     = 200;     // mot lan "nhan nut"

// Bat WiFi quet mang dinh ky de ESP32 keo dong ~100 mA nhu luc chay robot that.
// Chay khong WiFi thi chi ~40 mA — mach FM co the tu tat du robot that thi khong.
const bool LOAD_LIKE_ROBOT = true;

unsigned long lastPress = 0, lastBlink = 0, lastScan = 0;

// open-drain: chi KEO XUONG GND hoac THA NOI, khong bao gio day 3.3V vao K
void pressK() {
  digitalWrite(PIN_K, LOW);
  pinMode(PIN_K, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_K, LOW);
  delay(PRESS_MS);
  pinMode(PIN_K, INPUT);            // tha noi = nha nut
  for (int i = 0; i < 3; i++) {     // nhay nhanh 3 lan
    digitalWrite(PIN_LED, HIGH); delay(60);
    digitalWrite(PIN_LED, LOW);  delay(60);
  }
}

float read5V() {
  // cau chia doi: doc x2. analogReadMilliVolts da bu sai so ADC theo chip.
  return analogReadMilliVolts(PIN_SENSE) * 2 / 1000.0;
}

void setup() {
  pinMode(PIN_K, INPUT);            // luc khoi dong: tha noi, khong "nhan nham"
  pinMode(PIN_LED, OUTPUT);
  Serial.begin(115200);
  delay(300);
  Serial.println("\n### fm_keepalive ###");
  Serial.printf("nhan K moi %lu ms (0 = khong nhan), tai giong robot: %s\n",
                KEEPALIVE_MS, LOAD_LIKE_ROBOT ? "co" : "khong");
  if (LOAD_LIKE_ROBOT) WiFi.mode(WIFI_STA);
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);   // doc duoc toi ~3.1V
}

void loop() {
  unsigned long now = millis();

  if (KEEPALIVE_MS && now - lastPress >= KEEPALIVE_MS) {
    lastPress = now;
    pressK();
    Serial.printf("[%6lus] nhan K   5V ~ %.2f V (chi dung neu co cau chia ap)\n",
                  now / 1000, read5V());
  }

  if (now - lastBlink >= 1000) {
    lastBlink = now;
    digitalWrite(PIN_LED, HIGH); delay(40); digitalWrite(PIN_LED, LOW);
  }

  if (LOAD_LIKE_ROBOT && now - lastScan >= 10000) {
    lastScan = now;
    WiFi.scanNetworks(true);        // quet bat dong bo, khong chan loop
  }
}

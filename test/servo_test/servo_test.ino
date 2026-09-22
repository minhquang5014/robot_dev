/*
  Test servo SG90 + dang di Otto tren Arduino Uno.

  Dung DUNG cong thuc dao dong cua firmware Otto trong xiaozhi-esp32:
      goc = 90 + offset + bien_do * sin(2*pi*t/chu_ky + lech_pha)
  (oscillator.cc:125 va otto_movements.cc:301-311, 286, 514)
  Nen bien do / offset / trim chinh duoc o day chep thang sang
  otto_movements.cc va SetTrims() duoc, khong phai do lai tu dau.

  ---------------------------------------------------------------------------
  DAU DAY TIN HIEU  (day CAM hoac VANG cua servo)

      chan 9   -> LEFT_LEG     hong trai    (dua chan truoc/sau)
      chan 10  -> LEFT_FOOT    co chan trai (nghieng ban chan)
      chan 11  -> RIGHT_LEG    hong phai
      chan 6   -> RIGHT_FOOT   co chan phai

  ---------------------------------------------------------------------------
  CHI CHO PHEP 2 SERVO CHAY CUNG LUC  (MAX_ON)

  Uno cap qua USB chi chiu khoang 500mA. Bon servo cung luc la chac chan
  tut ap va board tu reset. Nen o day moi luc chi BAT toi da 2 con; con bi
  tat duoc NHA HAN (detach) nen khong an dong nao ca.

      Bam 1 2 3 4 de BAT / TAT tung servo.
      Dang bat 2 con ma bam con thu ba -> con BAT LAU NHAT tu dong tat.
      Bam lai chinh con dang bat -> tat con do.

  Co nguon ngoai 5V 2A roi thi bam `m` de nang gioi han len 4, khong can
  nap lai chuong trinh.

  ---------------------------------------------------------------------------
  CAP NGUON

      Nguon 5V 2A ---+--- (+) ---> day DO cua TAT CA servo
                     |
                     +--- (-) ---+--> day NAU/DEN cua TAT CA servo
                                 |
                                 +--> chan GND cua Uno     <== BAT BUOC

      Uno chan 9/10/11/6 ---------> day CAM/VANG tung servo

  Ba dieu tuyet doi:
    1. KHONG noi nguon 5V ngoai vao chan 5V cua Uno. Hai nguon danh nhau.
    2. PHAI chung GND. Khong chung thi xung PWM khong co moc tham chieu,
       servo giat loan hoac nam im.
    3. Tu 470-1000uF bac ngang 5V/GND NGAY SAT cum servo, de nuot xung dong.

  Chua co nguon ngoai thi lay 5V tu Uno, nhung phai cam Uno vao CU SAC TUONG,
  dung cam vao cong USB laptop (500mA va co the hong cong).

  ---------------------------------------------------------------------------
  LENH tren Serial Monitor (115200, khong can xuong dong):

    -- chon servo dang chay --
      1 2 3 4  : BAT/TAT  LEFT_LEG / LEFT_FOOT / RIGHT_LEG / RIGHT_FOOT
      m        : doi gioi han so servo chay cung luc (1 -> 2 -> 4)
      i        : xem con nao dang bat, goc, trim

    -- dang di (chi chay tren con dang BAT) --
      j        : NHAY
      t        : KHIENG CHAN, lac qua lai
      w / b    : DI TOI / di lui
      l / r    : quay trai / quay phai
      , / .    : giam / tang bien do (cang bia yeu thi giam)
      < / >    : cham / nhanh hon (doi chu ky)

    -- can chinh (tac dong len con vua bam so, tuc con dang chon) --
      c        : ve giua (90 do) — TU THE DE LAP CANG SERVO
      + / -    : nhich 1 do          [ / ] : nhich 5 do
      a<goc>   : di den goc tuyet doi, vd  a45
      z        : lay goc hien tai lam trim — chep so nay vao SetTrims()
      s        : quet cham 0->180->0
      d        : nha het servo
      h        : in lai bang lenh nay
*/
#include <Servo.h>

#define PIN_LEFT_LEG    9    // Thu vien Servo dung Timer1 -> chan 9 va 10 mat
#define PIN_LEFT_FOOT   10   // analogWrite(). Khong sao, o day khong can PWM.
#define PIN_RIGHT_LEG   11
#define PIN_RIGHT_FOOT  6

// Thu tu nay trung voi otto_movements.h de khoi nham khi chep so qua.
#define LEFT_LEG    0
#define RIGHT_LEG   1
#define LEFT_FOOT   2
#define RIGHT_FOOT  3
#define N           4

// SG90 chinh hang la 500-2400us cho 0-180 do. Thu vien Servo mac dinh 544-2400,
// nen nhieu con hang nhai khong voi toi duoc hai dau. Neu servo ri o hai dau
// thi keo hai so nay lai gan nhau.
#define PULSE_MIN     544
#define PULSE_MAX     2400

#define REFRESH_MS    20     // 50Hz, dung nhip lam tuoi cua servo
#define IDLE_RELEASE  5000   // khong co lenh gi qua 5 giay thi tu nha servo

Servo sv[N];
const int8_t pins[N]  = {PIN_LEFT_LEG, PIN_RIGHT_LEG, PIN_LEFT_FOOT, PIN_RIGHT_FOOT};
const char*  names[N] = {"LEFT_LEG", "RIGHT_LEG", "LEFT_FOOT", "RIGHT_FOOT"};

int   angle[N]    = {90, 90, 90, 90};   // goc dang giu (chua cong trim)
int   trim[N]     = {0, 0, 0, 0};       // bu lech co khi
bool  attached[N] = {false, false, false, false};

// Hang doi cac servo dang BAT, theo thu tu bat. onQ[0] la con bat lau nhat,
// tuc con se bi day ra khi bat them con moi ma da cham gioi han.
int8_t  onQ[N];
uint8_t nOn = 0;
uint8_t maxOn = 2;           // doi bang lenh `m`

int   period     = 1000;     // chu ky mac dinh cua Walk trong Otto
float ampScale   = 1.0;      // cang bia yeu thi ha xuong 0.5-0.7
uint8_t sel      = LEFT_LEG; // con dang chon de chinh trim
unsigned long lastCmd = 0;

bool has(uint8_t i) { return pins[i] >= 0; }

bool isOn(uint8_t i) {
  for (uint8_t k = 0; k < nOn; k++) if (onQ[k] == (int8_t)i) return true;
  return false;
}

void attachOne(uint8_t i) {
  if (!has(i) || attached[i]) return;
  sv[i].attach(pins[i], PULSE_MIN, PULSE_MAX);
  attached[i] = true;
}

void detachOne(uint8_t i) {
  if (!attached[i]) return;
  sv[i].detach();
  attached[i] = false;
}

void detachAll() {
  for (uint8_t i = 0; i < N; i++) detachOne(i);
  Serial.println(F("-- da nha het servo (van con BAT, se tu cam lai khi co lenh)"));
}

// Goc thuc xuat ra = goc mong muon + trim, chan trong 0..180.
// Con dang TAT thi bo qua hoan toan — khong cam, khong an dong.
void writeServo(uint8_t i, int deg) {
  if (!has(i) || !isOn(i)) return;
  angle[i] = constrain(deg, 0, 180);
  attachOne(i);
  sv[i].write(constrain(angle[i] + trim[i], 0, 180));
  lastCmd = millis();
}

void removeFromQ(uint8_t k) {
  for (uint8_t j = k; j + 1 < nOn; j++) onQ[j] = onQ[j + 1];
  nOn--;
}

void turnOff(uint8_t i) {
  detachOne(i);
  Serial.print(F("  TAT  ")); Serial.println(names[i]);
}

// Bam so -> bat neu dang tat, tat neu dang bat.
// Bat khi da day -> day con BAT LAU NHAT ra.
void toggleServo(uint8_t i) {
  if (!has(i)) { Serial.println(F("? servo nay chua khai chan")); return; }

  for (uint8_t k = 0; k < nOn; k++) {
    if (onQ[k] == (int8_t)i) {
      turnOff(i); removeFromQ(k);
      if (sel == i && nOn > 0) sel = onQ[nOn - 1];   // doi sang con con bat
      return;
    }
  }

  if (nOn >= maxOn) {
    uint8_t victim = onQ[0];
    Serial.print(F("  (cham gioi han ")); Serial.print(maxOn);
    Serial.println(F(" con, day con cu nhat ra)"));
    turnOff(victim);
    removeFromQ(0);
  }

  onQ[nOn++] = i;
  sel = i;                       // bat con nao thi chon luon con do de chinh
  attachOne(i);
  angle[i] = 90;
  sv[i].write(constrain(90 + trim[i], 0, 180));
  lastCmd = millis();
  Serial.print(F("  BAT  ")); Serial.println(names[i]);
}

// Di cham tung do mot. Servo di cham thi dong dinh thap hon nhieu so voi
// nhay mot phat — day cung la ly do Otto dung dao dong hinh sin.
void moveSlow(uint8_t i, int target, int msPerDeg) {
  if (!isOn(i)) { Serial.println(F("? servo nay dang TAT, bam so de bat")); return; }
  int from = angle[i];
  int step = (target > from) ? 1 : -1;
  for (int d = from; d != target; d += step) {
    writeServo(i, d);
    delay(msPerDeg);
  }
  writeServo(i, target);
}

// Noi suy tuyen tinh toi dich trong `ms`. Otto dung cach nay cho Jump
// (otto_movements.cc:286), khac han kieu dao dong sin ben duoi.
void moveServos(int ms, const int target[N]) {
  int from[N];
  for (uint8_t i = 0; i < N; i++) from[i] = angle[i];
  int steps = max(1, ms / REFRESH_MS);
  for (int s = 1; s <= steps; s++) {
    for (uint8_t i = 0; i < N; i++)
      if (isOn(i)) writeServo(i, from[i] + (long)(target[i] - from[i]) * s / steps);
    delay(REFRESH_MS);
  }
}

// Trai tim cua dang di Otto: cac servo cung dao dong hinh sin, khac nhau o
// LECH PHA. Chinh lech pha la doi han kieu di, khong phai doi bien do.
void oscillate(const int A[N], const int O[N], const int ph[N], float cycles) {
  unsigned long total = (unsigned long)(period * cycles);
  unsigned long t0 = millis(), t;
  while ((t = millis() - t0) < total) {
    for (uint8_t i = 0; i < N; i++) {
      if (!isOn(i)) continue;
      float rad = 2.0 * PI * (float)t / (float)period + radians(ph[i]);
      writeServo(i, 90 + O[i] + (int)lround(A[i] * ampScale * sin(rad)));
    }
    delay(REFRESH_MS);
  }
}

void home() {
  const int h[N] = {90, 90, 90, 90};
  moveServos(500, h);
  Serial.println(F("> tu the nghi. Lap cang servo O TU THE NAY."));
}

// otto_movements.cc:286 — hai co chan bat nguoc nhau roi ha ve.
void jump() {
  Serial.println(F("> NHAY"));
  const int up[N]   = {90, 90, 150, 30};
  const int down[N] = {90, 90,  90, 90};
  moveServos(period / 2, up);
  moveServos(period / 2, down);
}

// otto_movements.cc:514 — hai ban chan CUNG pha, nhung offset nguoc dau
// nen than nghieng han sang mot ben roi lac qua lai.
void tiptoe(int height, float cycles) {
  Serial.println(F("> KHIENG CHAN"));
  const int A[N]  = {0, 0, height,  height};
  const int O[N]  = {0, 0, height, -height};
  const int ph[N] = {0, 0, 0, 0};
  oscillate(A, O, ph, cycles);
  home();
}

// otto_movements.cc:301 — hai hong cung pha, hai ban chan cung pha, nhung
// hong lech ban chan 90 do. DAU cua 90 do quyet dinh tien hay lui:
// ban chan nghieng do don trong luong sang chan tru, dung luc hong dua
// chan kia ve truoc. Doi dau -> don trong luong lech nhip -> di lui.
void walk(int dir, float cycles) {
  Serial.println(dir > 0 ? F("> DI TOI") : F("> DI LUI"));
  const int A[N]  = {30, 30, 30, 30};
  const int O[N]  = { 0,  0,  5, -5};   // offset chan de hoi khieng len
  const int ph[N] = { 0,  0, dir * -90, dir * -90};
  oscillate(A, O, ph, cycles);
  home();
}

// Quay: hai hong dao dong bien do KHAC nhau -> mot ben buoc dai hon ben kia.
void turn(int dir, float cycles) {
  Serial.println(dir > 0 ? F("> QUAY TRAI") : F("> QUAY PHAI"));
  int A[N] = {30, 30, 20, 20};
  if (dir > 0) A[LEFT_LEG] = 10; else A[RIGHT_LEG] = 10;
  const int O[N]  = {0, 0, 4, -4};
  const int ph[N] = {0, 0, -90, -90};
  oscillate(A, O, ph, cycles);
  home();
}

void status() {
  Serial.println(F("--------------------------------"));
  for (uint8_t i = 0; i < N; i++) {
    Serial.print(i == sel ? F("  > ") : F("    "));
    Serial.print(isOn(i) ? F("[BAT] ") : F("[tat] "));
    Serial.print(names[i]);
    if (!has(i)) { Serial.println(F("   (chua khai chan)")); continue; }
    Serial.print(F("  chan=")); Serial.print(pins[i]);
    Serial.print(F("  goc="));  Serial.print(angle[i]);
    Serial.print(F("  trim=")); Serial.println(trim[i]);
  }
  Serial.print(F("  dang bat ")); Serial.print(nOn);
  Serial.print(F("/")); Serial.print(maxOn);
  Serial.print(F("   chu ky=")); Serial.print(period);
  Serial.print(F("ms   bien do x")); Serial.println(ampScale);
  Serial.println(F("--------------------------------"));
}

void help() {
  Serial.println(F("\n=== SERVO + DANG DI OTTO ==="));
  Serial.println(F(" chon servo chay:"));
  Serial.println(F("   1 LEFT_LEG  2 RIGHT_LEG  3 LEFT_FOOT  4 RIGHT_FOOT"));
  Serial.println(F("   bam de BAT/TAT. Qua gioi han -> con bat lau nhat tu tat."));
  Serial.println(F("   m doi gioi han (1/2/4)     i xem trang thai"));
  Serial.println(F(" dang di:"));
  Serial.println(F("   j nhay   t khieng chan   w di toi   b di lui"));
  Serial.println(F("   l quay trai   r quay phai   , . bien do   < > toc do"));
  Serial.println(F(" can chinh:"));
  Serial.println(F("   c ve giua   + - trim   [ ] trim 5   a<goc>   z lay trim"));
  Serial.println(F("   s quet   x LAC THU (chan doan)   d nha   h tro giup"));
  Serial.println(F("Thay '### BOOT ###' hien lai = Uno reset vi tut ap.\n"));
}

void setup() {
  Serial.begin(115200);
  delay(300);
  // Moc nay in mot lan duy nhat luc khoi dong. No hien lai giua bai test
  // nghia la board da reset — gan nhu chac chan do servo keo tut dien ap.
  Serial.println(F("\n### BOOT ###"));
  help();
  // Mac dinh bat mot chan hoan chinh (hong + co chan ben trai) — du de
  // kiem tra quan he lech pha giua hong va co chan.
  toggleServo(LEFT_LEG);
  toggleServo(LEFT_FOOT);
  status();
}

void loop() {
  // Nha servo khi ranh: SG90 giu tu the van an dien va ri rat kho chiu,
  // de lau con nong. Nha ra la het, va khong anh huong bai test.
  if (millis() - lastCmd > IDLE_RELEASE) {
    for (uint8_t i = 0; i < N; i++) if (attached[i]) { detachAll(); break; }
  }

  if (!Serial.available()) return;
  char cmd = Serial.read();
  if (cmd == '\n' || cmd == '\r' || cmd == ' ') return;
  lastCmd = millis();

  switch (cmd) {
    // ---- bat / tat servo ----
    case '1': toggleServo(LEFT_LEG);   status(); break;
    case '2': toggleServo(RIGHT_LEG);  status(); break;
    case '3': toggleServo(LEFT_FOOT);  status(); break;
    case '4': toggleServo(RIGHT_FOOT); status(); break;

    case 'm':
      maxOn = (maxOn == 1) ? 2 : (maxOn == 2 ? 4 : 1);
      Serial.print(F("> gioi han so servo chay cung luc = ")); Serial.println(maxOn);
      if (maxOn == 4) Serial.println(F("  (chi bat 4 khi da co nguon 5V ngoai!)"));
      while (nOn > maxOn) { turnOff(onQ[0]); removeFromQ(0); }
      status();
      break;

    // ---- dang di ----
    case 'j': jump(); break;
    case 't': tiptoe(20, 4); break;
    case 'w': walk(1, 4); break;
    case 'b': walk(-1, 4); break;
    case 'l': turn(1, 4); break;
    case 'r': turn(-1, 4); break;

    case ',': ampScale = max(0.2, ampScale - 0.1); status(); break;
    case '.': ampScale = min(1.5, ampScale + 0.1); status(); break;
    case '<': period = min(3000, period + 200); status(); break;
    case '>': period = max(400,  period - 200); status(); break;

    // ---- can chinh ----
    case 'c': home(); status(); break;

    case '+': writeServo(sel, angle[sel] + 1); status(); break;
    case '-': writeServo(sel, angle[sel] - 1); status(); break;
    case ']': writeServo(sel, angle[sel] + 5); status(); break;
    case '[': writeServo(sel, angle[sel] - 5); status(); break;

    case 'a': {
      // parseInt() het gio se tra ve 0, nen chi go moi chu 'a' la servo phang
      // ve 0 do. Bat buoc phai co it nhat mot chu so ngay sau 'a'.
      delay(20);                       // cho not ky tu con lai vao dem
      if (!isDigit(Serial.peek())) {
        Serial.println(F("? phai co so ngay sau a, vd: a45"));
        break;
      }
      int deg = Serial.parseInt();
      if (deg < 0 || deg > 180) {
        Serial.println(F("? goc phai trong khoang 0..180"));
        break;
      }
      Serial.print(F("> ")); Serial.print(names[sel]);
      Serial.print(F(" -> ")); Serial.println(deg);
      moveSlow(sel, deg, 8);           // di cham, cung ly le nhu moveSlow
      break;
    }

    case 'z':
      // Nhich den khi cang thang bang mat, roi bam z: do lech so voi 90
      // chinh la trim can nap vao Otto::SetTrims().
      trim[sel] += angle[sel] - 90;
      angle[sel] = 90;
      writeServo(sel, 90);
      Serial.print(F("> trim moi cua ")); Serial.print(names[sel]);
      Serial.print(F(" = ")); Serial.println(trim[sel]);
      break;

    case 's':
      Serial.print(F("> quet ")); Serial.println(names[sel]);
      moveSlow(sel, 0, 10);
      delay(300);
      moveSlow(sel, 180, 10);
      delay(300);
      moveSlow(sel, 90, 10);
      Serial.println(F("  xong. Servo ri o dau nao = cham gioi han co khi,"));
      Serial.println(F("  thu thu hep PULSE_MIN/PULSE_MAX roi nap lai."));
      break;

    case 'x': {
      // Chan doan: +-40 do, 15ms moi do -> moi chieu ~0.6s. Cham va rong
      // du de nhin ro. Chay lan luot tung con dang BAT.
      if (nOn == 0) { Serial.println(F("? khong con nao dang BAT")); break; }
      Serial.println(F("> LAC THU tung con dang BAT (+-40 do, cham)"));
      for (uint8_t k = 0; k < nOn; k++) {
        uint8_t i = onQ[k];
        Serial.print(F("  --> ")); Serial.print(names[i]);
        Serial.print(F("  (chan ")); Serial.print(pins[i]); Serial.println(F(")"));
        moveSlow(i,  50, 15); delay(400);
        moveSlow(i, 130, 15); delay(400);
        moveSlow(i,  90, 15); delay(400);
      }
      Serial.println(F("  xong. Con nao khong nhuc nhich = thieu nguon,"));
      Serial.println(F("  KHONG phai loi day tin hieu (day tin hieu sai thi"));
      Serial.println(F("  Arduino van bao nhan lenh nhu the nay)."));
      break;
    }

    case 'X': {
      // TEST THO — chan doan cuoi cung. Khong dung isOn/onQ/writeServo/trim,
      // khong dung ampScale, khong dung gioi han maxOn. Chi attach roi write,
      // tung chan MOT, de chi co dung mot servo an dong tai moi thoi diem.
      // Lenh nay ma van im thi loi 100% nam ngoai phan mem.
      Serial.println(F("> TEST THO: goi thang thu vien Servo, tung chan mot"));
      for (uint8_t i = 0; i < N; i++) {
        Serial.print(F("  --> ")); Serial.print(names[i]);
        Serial.print(F("   CHAN ")); Serial.println(pins[i]);
        sv[i].attach(pins[i]);                       // dai xung mac dinh
        for (int d =  90; d >=  40; d--) { sv[i].write(d); delay(15); }
        delay(400);
        for (int d =  40; d <= 140; d++) { sv[i].write(d); delay(15); }
        delay(400);
        for (int d = 140; d >=  90; d--) { sv[i].write(d); delay(15); }
        delay(400);
        sv[i].detach();
        attached[i] = false;
      }
      Serial.println(F("  xong TEST THO."));
      lastCmd = millis();
      break;
    }

    case 'P': {
      // Quet TOAN BO dai do rong xung, khong dung write(goc) ma dung
      // writeMicroseconds() truc tiep. SG90 nhan 500-2400us, MG90S nhieu con
      // chi nhan 1000-2000us. Quet ca dai nay thi moi loai servo deu phai
      // phan ung o dau do. Khong nhuc nhich o BAT KY xung nao = khong phai
      // chuyen dai xung, loai tru duoc gia thuyet cuoi cung thuoc phan mem.
      Serial.println(F("> QUET DAI XUNG 600-2400us, tung chan mot"));
      for (uint8_t i = 0; i < N; i++) {
        Serial.print(F("  --> ")); Serial.print(names[i]);
        Serial.print(F("   CHAN ")); Serial.println(pins[i]);
        sv[i].attach(pins[i], 400, 2600);       // mo rong hon ca chuan
        for (int us =  600; us <= 2400; us += 10) { sv[i].writeMicroseconds(us); delay(10); }
        delay(500);
        for (int us = 2400; us >=  600; us -= 10) { sv[i].writeMicroseconds(us); delay(10); }
        delay(500);
        sv[i].writeMicroseconds(1500);          // ve giua
        delay(400);
        sv[i].detach();
        attached[i] = false;
      }
      Serial.println(F("  xong QUET DAI XUNG."));
      lastCmd = millis();
      break;
    }

    case 'i': status(); break;
    case 'd': detachAll(); break;
    case 'h': help(); break;

    default:
      Serial.print(F("? lenh la: ")); Serial.println(cmd);
      break;
  }
}

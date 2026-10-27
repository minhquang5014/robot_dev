#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

// ESP32-S3-WROOM-1 N16R8 tren board DevKitC-1 44 chan, robot Otto 2 chan.
//
// Vi sao phai doi gan het chan so voi ban ESP32 cu (bread-compact-esp32):
//   - GPIO22..25 KHONG TON TAI tren S3 (chip nhay tu 21 sang 26).
//   - GPIO26..32 la chan SPI flash, khong duoc dung.
//   - GPIO33..37 bi PSRAM octal chiem. Con nay do duoc 8MB PSRAM (esptool bao
//     "Embedded PSRAM 8MB"), tuc ban R8 dung octal — nen 5 chan do mat that.
//   - GPIO19/20 la USB D-/D+.
//   - GPIO0/3/45/46 la chan strapping, 43/44 la UART0.
// Con lai an toan: 1,2,4..18,21,38..42,47,48. So do duoi deu nam trong do.

#define AUDIO_INPUT_SAMPLE_RATE  16000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

#define AUDIO_I2S_METHOD_SIMPLEX

#ifdef AUDIO_I2S_METHOD_SIMPLEX

#define AUDIO_I2S_MIC_GPIO_WS   GPIO_NUM_4
#define AUDIO_I2S_MIC_GPIO_SCK  GPIO_NUM_5
#define AUDIO_I2S_MIC_GPIO_DIN  GPIO_NUM_6

#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_7
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_15
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_16

#else

#define AUDIO_I2S_GPIO_WS   GPIO_NUM_4
#define AUDIO_I2S_GPIO_BCLK GPIO_NUM_5
#define AUDIO_I2S_GPIO_DIN  GPIO_NUM_6
#define AUDIO_I2S_GPIO_DOUT GPIO_NUM_7

#endif

#define BOOT_BUTTON_GPIO        GPIO_NUM_0
#define TOUCH_BUTTON_GPIO       GPIO_NUM_47
// Nut gia lap cau danh thuc. Ban ESP32 cu de o GPIO19 — tren S3 do la USB D-.
#define ASR_BUTTON_GPIO         GPIO_NUM_38
#define BUILTIN_LED_GPIO        GPIO_NUM_48

#define DISPLAY_SDA_PIN GPIO_NUM_41
#define DISPLAY_SCL_PIN GPIO_NUM_42
#define DISPLAY_WIDTH   128

#if CONFIG_OLED_SSD1306_128X32
#define DISPLAY_HEIGHT  32
#elif CONFIG_OLED_SSD1306_128X64 || CONFIG_OLED_SH1106_128X64
#define DISPLAY_HEIGHT  64
#else
#error "OLED display type is not selected"
#endif

#define DISPLAY_MIRROR_X true
#define DISPLAY_MIRROR_Y true

#define LAMP_GPIO GPIO_NUM_18

// Chan K cua module sac + tang ap FM5324GA (chay bang pin). Mach tu tat tang ap
// khi khong co ai "nhan nut", nen firmware nhan K theo nhip. Do ngay 26/10/2026
// (sketch test/fm_keepalive): nhan 200 ms moi 15 s giu 5V 33 phut lien, 132 lan
// nhan khong lan nao lam tat — chip khong hieu nhan ngan la bat/tat.
// K luc nghi chi ~0.8V nen noi thang, che do open-drain: chi keo xuong GND hoac
// tha noi, khong bao gio day 3.3V vao K. Khong lap module FM thi chan nay bo trong.
#define POWER_KEY_GPIO          GPIO_NUM_2
#define POWER_KEY_INTERVAL_MS   15000
#define POWER_KEY_PRESS_MS      200

// 4 servo chan. Giu nguyen 13 va 21 nhu ban ESP32 cu de chi phai doi 2 soi day;
// 22 va 23 thi bat buoc phai doi vi hai chan do khong ton tai tren S3.
#define OTTO_LEFT_LEG_GPIO   GPIO_NUM_13   // giu nguyen
#define OTTO_RIGHT_LEG_GPIO  GPIO_NUM_14   // doi tu 22
#define OTTO_LEFT_FOOT_GPIO  GPIO_NUM_21   // giu nguyen
#define OTTO_RIGHT_FOOT_GPIO GPIO_NUM_12   // doi tu 23

#endif // _BOARD_CONFIG_H_

#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

// VER2 — ESP32-S3-WROOM-1 N16R8 + man mau ST7789 240x240 (SPI) + Otto 2 chan.
//
// Khac ver1 o cho man hinh: ver1 dung OLED don sac 128x64 qua I2C (2 day),
// ver2 dung man mau 240x240 qua SPI (5 day) de chay bo 21 bieu cam GIF cua
// otto-emoji-gif-component — bo do ve san cho dung 240x240.
//
// Chan khong dung duoc tren S3, nhac lai de khoi cham vao:
//   GPIO22..25 khong ton tai | 26..32 SPI flash | 33..37 PSRAM octal (ban R8)
//   19/20 USB D-/D+ | 0/3/45/46 strapping | 43/44 UART0
// So do duoi chi dung trong vung an toan: 4..18, 21, 38..42, 47, 48.

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
#define ASR_BUTTON_GPIO         GPIO_NUM_38

// ---- Man mau ST7789 240x240 qua SPI ----
// Mo-dun 1.54" 240x240 pho bien co 7 chan: GND VCC SCL SDA RES DC BLK —
// KHONG co chan CS, nen de GPIO_NUM_NC. Neu mo-dun cua ban co CS thi gan chan
// that vao day, de NC se khong ra hinh.
#define DISPLAY_SPI_HOST        SPI3_HOST
#define DISPLAY_CLK_PIN         GPIO_NUM_18   // SCL
#define DISPLAY_MOSI_PIN        GPIO_NUM_17   // SDA
#define DISPLAY_DC_PIN          GPIO_NUM_8    // DC
#define DISPLAY_RST_PIN         GPIO_NUM_9    // RES
#define DISPLAY_BACKLIGHT_PIN   GPIO_NUM_10   // BLK
#define DISPLAY_CS_PIN          GPIO_NUM_NC

#define LCD_TYPE_ST7789_SERIAL
#define DISPLAY_WIDTH   240
#define DISPLAY_HEIGHT  240
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y false
#define DISPLAY_SWAP_XY  false
// Man IPS ST7789 thuong phai dao mau, khong dao thi hinh ra am ban.
#define DISPLAY_INVERT_COLOR true
#define DISPLAY_RGB_ORDER LCD_RGB_ELEMENT_ORDER_RGB
#define DISPLAY_OFFSET_X 0
#define DISPLAY_OFFSET_Y 0
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false
#define DISPLAY_SPI_MODE 3

// 4 servo chan — giu nguyen so do cua board S3 ver1 de day chuyen sang duoc.
#define OTTO_LEFT_LEG_GPIO   GPIO_NUM_13
#define OTTO_RIGHT_LEG_GPIO  GPIO_NUM_14
#define OTTO_LEFT_FOOT_GPIO  GPIO_NUM_21
#define OTTO_RIGHT_FOOT_GPIO GPIO_NUM_12

#endif // _BOARD_CONFIG_H_

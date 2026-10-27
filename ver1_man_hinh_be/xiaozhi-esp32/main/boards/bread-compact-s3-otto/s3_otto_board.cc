#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "mcp_server.h"
#include "lamp_controller.h"
#include "display/oled_display.h"

// Dung CHUNG ma nguon Otto voi board ESP32 cu thay vi chep lai ~1600 dong:
// sua dang di o mot noi thi ca hai board cung doi. oscillator.cc va
// otto_movements.cc duoc keo vao qua hai file boc cung thu muc nay, vi CMake
// chi gom boards/${BOARD_DIR}/*.cc.
#include "../bread-compact-esp32/otto_controller_simple.h"

#include <esp_log.h>
#include <esp_timer.h>
#include <driver/i2c_master.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>

#define TAG "BreadCompactS3Otto"

class BreadCompactS3OttoBoard : public WifiBoard {
private:
    Button boot_button_;
    Button touch_button_;
    Button asr_button_;

    esp_timer_handle_t power_key_timer_ = nullptr;
    esp_timer_handle_t power_key_release_timer_ = nullptr;

    i2c_master_bus_handle_t display_i2c_bus_;

    // Giu module FM5324GA khong tu tat: nhan K mot nhip ngan moi
    // POWER_KEY_INTERVAL_MS. Chay bang esp_timer nen khong chan task nao, va
    // khoi dong truoc moi thu khac de mach khong kip tu tat luc dang boot.
    // Open-drain: muc 0 = keo K xuong GND (nhan), muc 1 = tha noi (nha).
    void InitializePowerKey() {
        gpio_set_level(POWER_KEY_GPIO, 1);  // dat truoc khi bat chan: khong "nhan nham"
        gpio_config_t io_conf = {
            .pin_bit_mask = 1ULL << POWER_KEY_GPIO,
            .mode = GPIO_MODE_OUTPUT_OD,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_ERROR_CHECK(gpio_config(&io_conf));
        gpio_set_level(POWER_KEY_GPIO, 1);

        esp_timer_create_args_t release_args = {
            .callback = [](void*) { gpio_set_level(POWER_KEY_GPIO, 1); },
            .arg = nullptr,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "power_key_up",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&release_args, &power_key_release_timer_));

        esp_timer_create_args_t press_args = {
            .callback =
                [](void* arg) {
                    gpio_set_level(POWER_KEY_GPIO, 0);
                    esp_timer_start_once(static_cast<esp_timer_handle_t>(arg),
                                         POWER_KEY_PRESS_MS * 1000);
                },
            .arg = power_key_release_timer_,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "power_key",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&press_args, &power_key_timer_));
        ESP_ERROR_CHECK(esp_timer_start_periodic(power_key_timer_, POWER_KEY_INTERVAL_MS * 1000));
        ESP_LOGI(TAG, "Power key keepalive: GPIO%d, %d ms moi %d ms", POWER_KEY_GPIO,
                 POWER_KEY_PRESS_MS, POWER_KEY_INTERVAL_MS);
    }
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;
    Display* display_ = nullptr;

    void InitializeDisplayI2c() {
        i2c_master_bus_config_t bus_config = {
            .i2c_port = (i2c_port_t)0,
            .sda_io_num = DISPLAY_SDA_PIN,
            .scl_io_num = DISPLAY_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &display_i2c_bus_));
    }

    void InitializeSsd1306Display() {
        esp_lcd_panel_io_i2c_config_t io_config = {
            .dev_addr = 0x3C,
            .scl_speed_hz = 400 * 1000,
            .control_phase_bytes = 1,
            .dc_bit_offset = 6,
            .lcd_cmd_bits = 8,
            .lcd_param_bits = 8,
            .on_color_trans_done = nullptr,
            .user_ctx = nullptr,
            .flags = {
                .dc_low_on_data = 0,
                .disable_control_phase = 0,
            },
        };
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(display_i2c_bus_, &io_config, &panel_io_));

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = GPIO_NUM_NC;
        panel_config.bits_per_pixel = 1;

        esp_lcd_panel_ssd1306_config_t ssd1306_config = {
            .height = static_cast<uint8_t>(DISPLAY_HEIGHT),
        };
        panel_config.vendor_config = &ssd1306_config;

        ESP_ERROR_CHECK(esp_lcd_new_panel_ssd1306(panel_io_, &panel_config, &panel_));
        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_));
        if (esp_lcd_panel_init(panel_) != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize display");
            display_ = new NoDisplay();
            return;
        }
        ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_, true));

        display_ = new OledDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                   DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
    }

    void InitializeButtons() {
        gpio_config_t io_conf = {
            .pin_bit_mask = 1ULL << BUILTIN_LED_GPIO,
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        gpio_config(&io_conf);

        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                EnterWifiConfigMode();
                return;
            }
            gpio_set_level(BUILTIN_LED_GPIO, 1);
            app.ToggleChatState();
        });

        asr_button_.OnClick([this]() {
            // Phai trung voi model WakeNet dang bat (CONFIG_SR_WN_WN9_SOPHIA_TTS),
            // khong thi log va thong bao hien ten khac voi cau thuc su danh thuc.
            std::string wake_word = "Sophia";
            Application::GetInstance().WakeWordInvoke(wake_word);
        });

        touch_button_.OnPressDown([this]() {
            gpio_set_level(BUILTIN_LED_GPIO, 1);
            Application::GetInstance().StartListening();
        });
        touch_button_.OnPressUp([this]() {
            gpio_set_level(BUILTIN_LED_GPIO, 0);
            Application::GetInstance().StopListening();
        });
    }

    void InitializeTools() {
        static LampController lamp(LAMP_GPIO);
        static OttoController otto(OTTO_LEFT_LEG_GPIO, OTTO_RIGHT_LEG_GPIO,
                                   OTTO_LEFT_FOOT_GPIO, OTTO_RIGHT_FOOT_GPIO);
    }

public:
    BreadCompactS3OttoBoard()
        : WifiBoard(),
          boot_button_(BOOT_BUTTON_GPIO),
          touch_button_(TOUCH_BUTTON_GPIO),
          asr_button_(ASR_BUTTON_GPIO) {
        InitializePowerKey();
        InitializeDisplayI2c();
        InitializeSsd1306Display();
        InitializeButtons();
        InitializeTools();
    }

    virtual AudioCodec* GetAudioCodec() override {
#ifdef AUDIO_I2S_METHOD_SIMPLEX
        static NoAudioCodecSimplex audio_codec(
            AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK, AUDIO_I2S_SPK_GPIO_DOUT,
            AUDIO_I2S_MIC_GPIO_SCK, AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN);
#else
        static NoAudioCodecDuplex audio_codec(
            AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_BCLK, AUDIO_I2S_GPIO_WS, AUDIO_I2S_GPIO_DOUT, AUDIO_I2S_GPIO_DIN);
#endif
        return &audio_codec;
    }

    virtual Display* GetDisplay() override { return display_; }
};

DECLARE_BOARD(BreadCompactS3OttoBoard);

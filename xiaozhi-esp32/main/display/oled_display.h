#ifndef OLED_DISPLAY_H
#define OLED_DISPLAY_H

#include "lvgl_display.h"

#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>

class OledDisplay : public LvglDisplay {
private:
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;

    lv_obj_t* top_bar_ = nullptr;
    lv_obj_t* status_bar_ = nullptr;
    lv_obj_t* content_ = nullptr;
    lv_obj_t* content_left_ = nullptr;
    lv_obj_t* content_right_ = nullptr;
    lv_obj_t* container_ = nullptr;
    lv_obj_t* side_bar_ = nullptr;
    lv_obj_t* emotion_label_ = nullptr;
    lv_obj_t* chat_message_label_ = nullptr;

    // Cặp "mắt" tối giản, tự vẽ (không dùng font icon/emoji có sẵn) — 2 hình
    // bo góc đối xứng, đổi kích thước/độ bo/góc nghiêng theo cảm xúc, có
    // chuyển động mượt (LVGL style transition) và tự chớp mắt định kỳ.
    lv_obj_t* eyes_area_ = nullptr;
    lv_obj_t* left_eye_ = nullptr;
    lv_obj_t* right_eye_ = nullptr;
    lv_timer_t* eye_blink_timer_ = nullptr;
    std::string current_eye_emotion_ = "neutral";
    bool eyes_blinking_ = false;

    // Mí mắt: chỉ hiện khi biểu lộ cảm xúc (bình thường chỉ có mắt). Mỗi mắt
    // có một dãy cột hẹp che phần trên — chiều cao mỗi cột khác nhau để tạo mí
    // nghiêng (giận/buồn) mà không cần xoay đối tượng — và một thanh che phần
    // dưới (mắt cười).
    static constexpr int kLidCols = 9;
    static constexpr int kLidColW = 4;
    lv_obj_t* top_lid_[2][kLidCols] = {};
    lv_obj_t* bottom_lid_[2][kLidCols] = {};
    uint32_t emotion_set_tick_ = 0;
    lv_timer_t* neutral_timer_ = nullptr;

    virtual bool Lock(int timeout_ms = 0) override;
    virtual void Unlock() override;

    void SetupUI_128x64();
    void SetupUI_128x32();
    void SetEyeEmotion_128x64(const char* emotion);
    void ApplyEyeEmotionNow(const std::string& emotion);
    void ApplyLids(int eye_index, int eye_w, int eye_h, int top_cover, int slope_pct, int top_curve,
                   int bottom_cover, int bottom_curve);
    void BlinkEyesOnce();
    static void EyeBlinkTimerCallback(lv_timer_t* timer);

public:
    OledDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                int height, bool mirror_x, bool mirror_y);
    ~OledDisplay();

    virtual void SetupUI() override;
    virtual void SetChatMessage(const char* role, const char* content) override;
    virtual void SetEmotion(const char* emotion) override;
    virtual void SetTheme(Theme* theme) override;
    virtual bool IsMonochrome() const override { return true; }
    void SetPowerSaveMode(bool on) override;
};

#endif  // OLED_DISPLAY_H

#include "oled_display.h"
#include "assets/lang_config.h"
#include "lvgl_font.h"
#include "lvgl_theme.h"
#include "settings.h"

#include <algorithm>
#include <string>

#include <esp_err.h>
#include <esp_log.h>
#include <esp_lvgl_port.h>
#include <esp_random.h>
#include <material_symbols.h>
#include <noto_emoji.h>

#define TAG "OledDisplay"

LV_FONT_DECLARE(BUILTIN_TEXT_FONT);
LV_FONT_DECLARE(BUILTIN_ICON_FONT);
LV_FONT_DECLARE(font_material_symbols_30_1);
LV_FONT_DECLARE(font_noto_emoji_30_1);

OledDisplay::OledDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                         int width, int height, bool mirror_x, bool mirror_y)
    : panel_io_(panel_io), panel_(panel) {
    width_ = width;
    height_ = height;

    auto text_font = std::make_shared<LvglBuiltInFont>(&BUILTIN_TEXT_FONT);
    auto icon_font = std::make_shared<LvglBuiltInFont>(&BUILTIN_ICON_FONT);
    auto large_icon_font = std::make_shared<LvglBuiltInFont>(&font_material_symbols_30_1);
    auto emoji_font = std::make_shared<LvglBuiltInFont>(&font_noto_emoji_30_1);

    auto dark_theme = new LvglTheme("dark");
    dark_theme->set_text_font(text_font);
    dark_theme->set_icon_font(icon_font);
    dark_theme->set_large_icon_font(large_icon_font);
    dark_theme->set_emoji_font(emoji_font);

    auto& theme_manager = LvglThemeManager::GetInstance();
    theme_manager.RegisterTheme("dark", dark_theme);
    current_theme_ = dark_theme;

    ESP_LOGI(TAG, "Initialize LVGL");
    lvgl_port_cfg_t port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    port_cfg.task_priority = 1;
    port_cfg.task_stack = 6144;
#if CONFIG_SOC_CPU_CORES_NUM > 1
    port_cfg.task_affinity = 1;
#endif
    lvgl_port_init(&port_cfg);

    ESP_LOGI(TAG, "Adding OLED display");
    const lvgl_port_display_cfg_t display_cfg = {
        .io_handle = panel_io_,
        .panel_handle = panel_,
        .control_handle = nullptr,
        .buffer_size = static_cast<uint32_t>(width_ * height_),
        .double_buffer = false,
        .trans_size = 0,
        .hres = static_cast<uint32_t>(width_),
        .vres = static_cast<uint32_t>(height_),
        .monochrome = true,
        .rotation =
            {
                .swap_xy = false,
                .mirror_x = mirror_x,
                .mirror_y = mirror_y,
            },
        .flags =
            {
                .buff_dma = 1,
                .buff_spiram = 0,
                .sw_rotate = 0,
                .full_refresh = 0,
                .direct_mode = 0,
            },
    };

    display_ = lvgl_port_add_disp(&display_cfg);
    if (display_ == nullptr) {
        ESP_LOGE(TAG, "Failed to add display");
        return;
    }

    // Note: SetupUI() should be called by Application::Initialize(), not in constructor
    // to ensure lvgl objects are created after the display is fully initialized.
}

void OledDisplay::SetupUI() {
    // Prevent duplicate calls - if already called, return early
    if (setup_ui_called_) {
        ESP_LOGW(TAG, "SetupUI() called multiple times, skipping duplicate call");
        return;
    }

    Display::SetupUI();  // Mark SetupUI as called
    if (height_ == 64) {
        SetupUI_128x64();
    } else {
        SetupUI_128x32();
    }
}

OledDisplay::~OledDisplay() {
    if (content_ != nullptr) {
        lv_obj_del(content_);
    }

    bool is_128x64_layout = (top_bar_ != nullptr);
    if (status_bar_ != nullptr && is_128x64_layout) {
        status_label_ = nullptr;
        notification_label_ = nullptr;
        lv_obj_del(status_bar_);
    }
    if (top_bar_ != nullptr) {
        network_label_ = nullptr;
        mute_label_ = nullptr;
        battery_label_ = nullptr;
        lv_obj_del(top_bar_);
    }
    if (side_bar_ != nullptr) {
        if (!is_128x64_layout) {
            status_label_ = nullptr;
            notification_label_ = nullptr;
            network_label_ = nullptr;
            mute_label_ = nullptr;
            battery_label_ = nullptr;
        }
        lv_obj_del(side_bar_);
    }
    if (container_ != nullptr) {
        lv_obj_del(container_);
    }

    if (panel_ != nullptr) {
        esp_lcd_panel_del(panel_);
    }
    if (panel_io_ != nullptr) {
        esp_lcd_panel_io_del(panel_io_);
    }
    lvgl_port_deinit();
}

bool OledDisplay::Lock(int timeout_ms) { return lvgl_port_lock(timeout_ms); }

void OledDisplay::Unlock() { lvgl_port_unlock(); }

void OledDisplay::SetChatMessage(const char* role, const char* content) {
    DisplayLockGuard lock(this);
    if (chat_message_label_ == nullptr) {
        return;
    }

    // Replace all newlines with spaces
    std::string content_str = content;
    std::replace(content_str.begin(), content_str.end(), '\n', ' ');

    lv_anim_delete(chat_message_label_, nullptr);
    if (content_right_ == nullptr) {
        lv_label_set_text(chat_message_label_, content_str.c_str());
    } else {
        if (content == nullptr || content[0] == '\0') {
            lv_obj_add_flag(content_right_, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_label_set_text(chat_message_label_, content_str.c_str());
            lv_obj_remove_flag(content_right_, LV_OBJ_FLAG_HIDDEN);
        }
    }
}

void OledDisplay::SetupUI_128x64() {
    DisplayLockGuard lock(this);

    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto large_icon_font = lvgl_theme->large_icon_font()->font();

    auto screen = lv_screen_active();
    lv_obj_set_style_text_font(screen, text_font, 0);
    lv_obj_set_style_text_color(screen, lv_color_black(), 0);

    /* Container */
    container_ = lv_obj_create(screen);
    lv_obj_set_size(container_, LV_HOR_RES, LV_VER_RES);
    lv_obj_set_flex_flow(container_, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(container_, 0, 0);
    lv_obj_set_style_border_width(container_, 0, 0);
    lv_obj_set_style_pad_row(container_, 0, 0);

    /* Layer 1: Top bar - for status icons */
    top_bar_ = lv_obj_create(container_);
    lv_obj_set_size(top_bar_, LV_HOR_RES, 16);
    lv_obj_set_style_radius(top_bar_, 0, 0);
    lv_obj_set_style_bg_opa(top_bar_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(top_bar_, 0, 0);
    lv_obj_set_style_pad_all(top_bar_, 0, 0);
    lv_obj_set_flex_flow(top_bar_, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(top_bar_, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_set_scrollbar_mode(top_bar_, LV_SCROLLBAR_MODE_OFF);

    network_label_ = lv_label_create(top_bar_);
    lv_label_set_text(network_label_, "");
    lv_obj_set_style_text_font(network_label_, icon_font, 0);

    lv_obj_t* right_icons = lv_obj_create(top_bar_);
    lv_obj_set_size(right_icons, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_opa(right_icons, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(right_icons, 0, 0);
    lv_obj_set_style_pad_all(right_icons, 0, 0);
    lv_obj_set_flex_flow(right_icons, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(right_icons, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);

    mute_label_ = lv_label_create(right_icons);
    lv_label_set_text(mute_label_, "");
    lv_obj_set_style_text_font(mute_label_, icon_font, 0);

    battery_label_ = lv_label_create(right_icons);
    lv_label_set_text(battery_label_, "");
    lv_obj_set_style_text_font(battery_label_, icon_font, 0);

    // Không dùng status_bar_/chat_message_label_ dạng chữ trên bố cục này —
    // để trống cho 2 "mắt" chiếm toàn bộ phần còn lại. Vẫn khởi tạo các label
    // (ẩn, không gắn vào cây UI) để không phá interface SetChatMessage()/status
    // ở nơi khác gọi tới — chúng chỉ đơn giản không hiển thị gì.
    status_bar_ = nullptr;
    notification_label_ = lv_label_create(screen);
    lv_obj_add_flag(notification_label_, LV_OBJ_FLAG_HIDDEN);
    status_label_ = lv_label_create(screen);
    lv_obj_add_flag(status_label_, LV_OBJ_FLAG_HIDDEN);
    chat_message_label_ = lv_label_create(screen);
    lv_obj_add_flag(chat_message_label_, LV_OBJ_FLAG_HIDDEN);
    content_right_ = nullptr;

    /* Content: cap "mat" toi gian, chiem toan bo phan con lai duoi top_bar_ */
    content_ = lv_obj_create(container_);
    lv_obj_set_scrollbar_mode(content_, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_style_radius(content_, 0, 0);
    lv_obj_set_style_pad_all(content_, 0, 0);
    lv_obj_set_style_border_width(content_, 0, 0);
    lv_obj_set_width(content_, LV_HOR_RES);
    lv_obj_set_flex_grow(content_, 1);

    eyes_area_ = lv_obj_create(content_);
    lv_obj_set_size(eyes_area_, LV_HOR_RES, LV_SIZE_CONTENT);
    lv_obj_set_style_pad_all(eyes_area_, 0, 0);
    lv_obj_set_style_border_width(eyes_area_, 0, 0);
    lv_obj_set_style_bg_opa(eyes_area_, LV_OPA_TRANSP, 0);
    lv_obj_set_flex_flow(eyes_area_, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(eyes_area_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(eyes_area_, 12, 0);
    lv_obj_center(eyes_area_);

    // Chuyển động mượt khi đổi hình dạng mắt: LVGL tự nội suy width/height/
    // radius/góc xoay từ giá trị cũ sang mới trong 180ms, không cần tự viết
    // animation thủ công.
    static const lv_style_prop_t eye_transition_props[] = {
        LV_STYLE_WIDTH, LV_STYLE_HEIGHT, LV_STYLE_RADIUS,
        LV_STYLE_TRANSFORM_ROTATION, LV_STYLE_PROP_INV,
    };
    static lv_style_transition_dsc_t eye_transition;
    lv_style_transition_dsc_init(&eye_transition, eye_transition_props, lv_anim_path_ease_out,
                                 180, 0, nullptr);

    left_eye_ = lv_obj_create(eyes_area_);
    lv_obj_set_style_border_width(left_eye_, 0, 0);
    lv_obj_set_style_bg_color(left_eye_, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(left_eye_, LV_OPA_COVER, 0);
    lv_obj_set_style_transition(left_eye_, &eye_transition, 0);

    right_eye_ = lv_obj_create(eyes_area_);
    lv_obj_set_style_border_width(right_eye_, 0, 0);
    lv_obj_set_style_bg_color(right_eye_, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(right_eye_, LV_OPA_COVER, 0);
    lv_obj_set_style_transition(right_eye_, &eye_transition, 0);

    // Mí mắt: cùng màu nền để "khoét" bớt mắt. Mắt tự cắt phần con vượt ra
    // ngoài, nên cột thừa bề ngang không lộ ra ngoài. Cả mí trên lẫn mí dưới là
    // một dãy cột hẹp; chiều cao (và vị trí y cho mí dưới) từng cột được đặt
    // riêng để tạo mí nghiêng hoặc cong mà không cần xoay đối tượng.
    static lv_style_transition_dsc_t lid_transition;
    static const lv_style_prop_t lid_transition_props[] = {LV_STYLE_HEIGHT, LV_STYLE_Y,
                                                           LV_STYLE_PROP_INV};
    lv_style_transition_dsc_init(&lid_transition, lid_transition_props, lv_anim_path_ease_out, 180,
                                 0, nullptr);
    lv_obj_t* eyes[2] = {left_eye_, right_eye_};
    for (int e = 0; e < 2; e++) {
        lv_obj_remove_flag(eyes[e], LV_OBJ_FLAG_SCROLLABLE);
        auto make_col = [&](int i) {
            lv_obj_t* col = lv_obj_create(eyes[e]);
            lv_obj_remove_flag(col, LV_OBJ_FLAG_SCROLLABLE);
            lv_obj_remove_flag(col, LV_OBJ_FLAG_CLICKABLE);
            lv_obj_set_style_border_width(col, 0, 0);
            lv_obj_set_style_radius(col, 0, 0);
            lv_obj_set_style_pad_all(col, 0, 0);
            lv_obj_set_style_bg_color(col, lv_color_white(), 0);
            lv_obj_set_style_bg_opa(col, LV_OPA_COVER, 0);
            lv_obj_set_style_transition(col, &lid_transition, 0);
            lv_obj_set_size(col, kLidColW, 0);
            lv_obj_set_pos(col, i * kLidColW, 0);
            return col;
        };
        for (int i = 0; i < kLidCols; i++) {
            top_lid_[e][i] = make_col(i);
            bottom_lid_[e][i] = make_col(i);
        }
    }

    // emotion_label_ khong dung tren bo cuc nay nua, giu con tro null-safe
    emotion_label_ = nullptr;

    // Tu chop mat dinh ky (3.2-5.5s/lan) de robot co cam giac "song", khong
    // dung im.
    eye_blink_timer_ = lv_timer_create(EyeBlinkTimerCallback, 4000, this);
    lv_timer_set_repeat_count(eye_blink_timer_, -1);

    SetEyeEmotion_128x64("neutral");

    low_battery_popup_ = lv_obj_create(screen);
    lv_obj_set_scrollbar_mode(low_battery_popup_, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_size(low_battery_popup_, LV_HOR_RES * 0.9, text_font->line_height * 2);
    lv_obj_align(low_battery_popup_, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(low_battery_popup_, lv_color_black(), 0);
    lv_obj_set_style_radius(low_battery_popup_, 10, 0);
    low_battery_label_ = lv_label_create(low_battery_popup_);
    lv_label_set_text(low_battery_label_, Lang::Strings::BATTERY_NEED_CHARGE);
    lv_obj_set_style_text_color(low_battery_label_, lv_color_white(), 0);
    lv_obj_center(low_battery_label_);
    lv_obj_add_flag(low_battery_popup_, LV_OBJ_FLAG_HIDDEN);
}

void OledDisplay::SetupUI_128x32() {
    DisplayLockGuard lock(this);

    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto large_icon_font = lvgl_theme->large_icon_font()->font();

    auto screen = lv_screen_active();
    lv_obj_set_style_text_font(screen, text_font, 0);

    /* Container */
    container_ = lv_obj_create(screen);
    lv_obj_set_size(container_, LV_HOR_RES, LV_VER_RES);
    lv_obj_set_flex_flow(container_, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_all(container_, 0, 0);
    lv_obj_set_style_border_width(container_, 0, 0);
    lv_obj_set_style_pad_column(container_, 0, 0);

    /* Emotion label on the left side */
    content_ = lv_obj_create(container_);
    lv_obj_set_size(content_, 32, 32);
    lv_obj_set_style_pad_all(content_, 0, 0);
    lv_obj_set_style_border_width(content_, 0, 0);
    lv_obj_set_style_radius(content_, 0, 0);

    emotion_label_ = lv_label_create(content_);
    lv_obj_set_style_text_font(emotion_label_, large_icon_font, 0);
    lv_label_set_text(emotion_label_, MATERIAL_SYMBOLS_ROBOT_2);
    lv_obj_center(emotion_label_);

    /* Right side */
    side_bar_ = lv_obj_create(container_);
    lv_obj_set_size(side_bar_, width_ - 32, 32);
    lv_obj_set_flex_flow(side_bar_, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(side_bar_, 0, 0);
    lv_obj_set_style_border_width(side_bar_, 0, 0);
    lv_obj_set_style_radius(side_bar_, 0, 0);
    lv_obj_set_style_pad_row(side_bar_, 0, 0);

    /* Status bar */
    status_bar_ = lv_obj_create(side_bar_);
    lv_obj_set_size(status_bar_, width_ - 32, 16);
    lv_obj_set_style_radius(status_bar_, 0, 0);
    lv_obj_set_flex_flow(status_bar_, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_all(status_bar_, 0, 0);
    lv_obj_set_style_border_width(status_bar_, 0, 0);
    lv_obj_set_style_pad_column(status_bar_, 0, 0);

    status_label_ = lv_label_create(status_bar_);
    lv_obj_set_flex_grow(status_label_, 1);
    lv_obj_set_style_pad_left(status_label_, 2, 0);
    lv_label_set_text(status_label_, Lang::Strings::INITIALIZING);

    notification_label_ = lv_label_create(status_bar_);
    lv_obj_set_flex_grow(notification_label_, 1);
    lv_obj_set_style_pad_left(notification_label_, 2, 0);
    lv_label_set_text(notification_label_, "");
    lv_obj_add_flag(notification_label_, LV_OBJ_FLAG_HIDDEN);

    mute_label_ = lv_label_create(status_bar_);
    lv_label_set_text(mute_label_, "");
    lv_obj_set_style_text_font(mute_label_, icon_font, 0);

    network_label_ = lv_label_create(status_bar_);
    lv_label_set_text(network_label_, "");
    lv_obj_set_style_text_font(network_label_, icon_font, 0);

    battery_label_ = lv_label_create(status_bar_);
    lv_label_set_text(battery_label_, "");
    lv_obj_set_style_text_font(battery_label_, icon_font, 0);

    chat_message_label_ = lv_label_create(side_bar_);
    lv_obj_set_size(chat_message_label_, width_ - 32, LV_SIZE_CONTENT);
    lv_obj_set_style_pad_left(chat_message_label_, 2, 0);
    lv_label_set_long_mode(chat_message_label_, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_label_set_text(chat_message_label_, "");

    // Start scrolling subtitle after a delay
    static lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_delay(&a, 1000);
    lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
    lv_obj_set_style_anim(chat_message_label_, &a, LV_PART_MAIN);
    lv_obj_set_style_anim_duration(chat_message_label_, lv_anim_speed_clamped(60, 300, 60000),
                                   LV_PART_MAIN);
}

// Bộ "mắt" tối giản tự thiết kế (không dùng icon/emoji có sẵn). Bình thường
// chỉ có 2 mắt vuông bo góc; khi biểu lộ cảm xúc thì đổi kích thước và thêm mí
// che phần trên/dưới mắt, có thể nghiêng hoặc cong, và hai mắt có thể khác
// nhau (nghi ngờ, cà khịa). Chỉ dùng hình học cơ bản, không có miệng/chữ.
struct EyeShape {
    int16_t w, h;
    int16_t top_cover;     // px che từ đỉnh mắt, tính ở giữa mắt
    int16_t top_slope;     // % độ dốc mí trên; dương = phía trong thấp hơn (giận)
    int16_t top_curve;     // px che thêm ở hai mép so với giữa (mí trên cong vòm)
    int16_t bottom_cover;  // px che từ đáy mắt, tính ở giữa mắt
    int16_t bottom_curve;  // px thay đổi ở hai mép (âm = che ít hơn ở mép)
};
struct EyePair {
    EyeShape left, right;
};

static EyePair Same(EyeShape s) { return {s, s}; }

// Độ bo góc cố định cho mọi cảm xúc — vuông bo góc, cạnh thẳng ở giữa.
static constexpr int16_t kEyeCornerRadius = 9;

static EyePair GetEyePairForEmotion(const std::string& e) {
    //                        w   h  top slope curve bot bcurve
    // Ngạc nhiên / sốc: mắt to hơn, không mí
    if (e == "surprised" || e == "shocked") return Same({30, 36, 0, 0, 0, 0, 0});
    // Vui: đáy mắt bị che phẳng -> hình vòm úp
    if (e == "happy" || e == "silly" || e == "delicious" || e == "loving" || e == "kissy")
        return Same({28, 30, 0, 0, 0, 13, 0});
    // Cười lớn: mắt thành vòng cung mảnh ⌒ (mí trên và mí dưới cùng cong)
    if (e == "laughing" || e == "funny") return Same({30, 28, 0, 0, 10, 21, -10});
    // Giận: mí trên dốc xuống phía trong, đáy hơi nâng
    if (e == "angry") return Same({28, 30, 12, 55, 0, 3, 0});
    // Buồn: mí trên dốc ngược, phía ngoài sụp xuống
    if (e == "sad" || e == "crying") return Same({28, 30, 9, -55, 0, 2, 0});
    // Ngượng: mí trên hạ nhẹ + đáy nâng, mắt nhìn né
    if (e == "embarrassed") return Same({26, 30, 6, -25, 0, 6, 0});
    // Bối rối / nghi ngờ: bất đối xứng — một mắt mí hạ thấp hơn
    if (e == "confused")
        return {{26, 32, 3, 0, 0, 0, 0}, {26, 32, 13, 0, 0, 0, 0}};
    // Suy nghĩ: mắt nhỏ lại, mí trên hạ
    if (e == "thinking") return Same({24, 28, 6, 0, 0, 4, 0});
    // Buồn ngủ: chỉ còn khe hẹp
    if (e == "sleepy") return Same({30, 32, 16, 0, 0, 10, 0});
    // Thư giãn: mí hạ nửa mắt, đáy hơi nâng
    if (e == "relaxed") return Same({30, 32, 12, 0, 0, 8, 0});
    // Tự tin / cà khịa: mí phẳng hạ nửa mắt, bất đối xứng nhẹ (nhếch mắt)
    if (e == "confident" || e == "cool")
        return {{30, 32, 14, 0, 0, 6, 0}, {30, 32, 11, 0, 0, 6, 0}};
    // neutral, winking (xử lý riêng) và mọi cảm xúc chưa liệt kê: chỉ có mắt
    return Same({26, 32, 0, 0, 0, 0, 0});
}

static void ApplyEyeShape(lv_obj_t* eye, const EyeShape& s) {
    lv_obj_set_size(eye, s.w, s.h);
    lv_obj_set_style_radius(eye, kEyeCornerRadius, 0);
}

// Đặt chiều cao từng cột mí. Cột i nằm ở tâm x = i*kLidColW + kLidColW/2;
// độ dốc nhân với dấu của mắt (mắt phải đối xứng mắt trái). u = vị trí chuẩn
// hóa (-1..1) từ tâm mắt ra mép, dùng cho độ cong parabol.
void OledDisplay::ApplyLids(int eye_index, int eye_w, int eye_h, int top_cover, int slope_pct,
                            int top_curve, int bottom_cover, int bottom_curve) {
    int sign = (eye_index == 0) ? 1 : -1;
    int half = eye_w / 2 > 0 ? eye_w / 2 : 1;
    for (int i = 0; i < kLidCols; i++) {
        int dx = i * kLidColW + kLidColW / 2 - eye_w / 2;
        int u2_pct = dx * dx * 100 / (half * half);  // u^2 * 100
        if (u2_pct > 100) u2_pct = 100;

        int top = 0;
        if (top_cover > 0 || top_curve != 0) {
            top = top_cover + sign * slope_pct * dx / 100 + top_curve * u2_pct / 100;
            if (top < 0) top = 0;
            if (top > eye_h) top = eye_h;
        }
        lv_obj_set_height(top_lid_[eye_index][i], top);

        int bot = 0;
        if (bottom_cover > 0) {
            bot = bottom_cover + bottom_curve * u2_pct / 100;
            if (bot < 0) bot = 0;
            if (bot > eye_h) bot = eye_h;
        }
        lv_obj_set_y(bottom_lid_[eye_index][i], eye_h - bot);
        lv_obj_set_height(bottom_lid_[eye_index][i], bot);
    }
}

void OledDisplay::ApplyEyeEmotionNow(const std::string& e) {
    current_eye_emotion_ = e;
    if (eyes_blinking_) {
        // Đang giữa nhịp chớp mắt — cảm xúc mới được áp dụng ngay khi mắt mở lại.
        return;
    }
    EyePair pair = GetEyePairForEmotion(e);
    if (e == "winking") {
        // Mắt trái mở bình thường, mắt phải nheo thành khe — vui tinh nghịch
        pair = {{26, 32, 0, 0, 0, 0, 0}, {26, 32, 14, 0, 0, 14, 0}};
    }
    ApplyEyeShape(left_eye_, pair.left);
    ApplyEyeShape(right_eye_, pair.right);
    ApplyLids(0, pair.left.w, pair.left.h, pair.left.top_cover, pair.left.top_slope,
              pair.left.top_curve, pair.left.bottom_cover, pair.left.bottom_curve);
    ApplyLids(1, pair.right.w, pair.right.h, pair.right.top_cover, pair.right.top_slope,
              pair.right.top_curve, pair.right.bottom_cover, pair.right.bottom_curve);
}

void OledDisplay::SetEyeEmotion_128x64(const char* emotion) {
    if (left_eye_ == nullptr || right_eye_ == nullptr) {
        return;
    }
    std::string e = emotion ? emotion : "neutral";
    constexpr uint32_t kHoldMs = 5000;  // giữ cảm xúc tối thiểu 5 giây

    if (neutral_timer_ != nullptr) {
        lv_timer_delete(neutral_timer_);
        neutral_timer_ = nullptr;
    }
    if (e == "neutral" && current_eye_emotion_ != "neutral") {
        // Firmware trả về "neutral" ngay khi robot nói xong -> trì hoãn để cảm
        // xúc còn kịp nhìn thấy.
        uint32_t elapsed = lv_tick_elaps(emotion_set_tick_);
        if (elapsed < kHoldMs) {
            neutral_timer_ = lv_timer_create(
                [](lv_timer_t* t) {
                    auto* self = static_cast<OledDisplay*>(lv_timer_get_user_data(t));
                    self->neutral_timer_ = nullptr;
                    self->ApplyEyeEmotionNow("neutral");
                    lv_timer_delete(t);
                },
                kHoldMs - elapsed, this);
            lv_timer_set_repeat_count(neutral_timer_, 1);
            return;
        }
    }
    if (e != "neutral") {
        emotion_set_tick_ = lv_tick_get();
    }
    ApplyEyeEmotionNow(e);
}

void OledDisplay::BlinkEyesOnce() {
    if (left_eye_ == nullptr || right_eye_ == nullptr || eyes_blinking_) {
        return;
    }
    eyes_blinking_ = true;
    // Nhắm nhanh (height ~3px, tận dụng transition 180ms đã khai báo)
    lv_obj_set_height(left_eye_, 3);
    lv_obj_set_height(right_eye_, 3);
    lv_obj_set_style_radius(left_eye_, kEyeCornerRadius, 0);
    lv_obj_set_style_radius(right_eye_, kEyeCornerRadius, 0);

    // Sau 180ms (đúng lúc animation nhắm mắt xong), mở lại đúng hình dạng
    // của cảm xúc hiện tại.
    lv_timer_t* reopen = lv_timer_create(
        [](lv_timer_t* t) {
            auto* self = static_cast<OledDisplay*>(lv_timer_get_user_data(t));
            self->eyes_blinking_ = false;
            self->ApplyEyeEmotionNow(self->current_eye_emotion_);
            lv_timer_delete(t);
        },
        180, this);
    lv_timer_set_repeat_count(reopen, 1);
}

void OledDisplay::EyeBlinkTimerCallback(lv_timer_t* timer) {
    auto* self = static_cast<OledDisplay*>(lv_timer_get_user_data(timer));
    self->BlinkEyesOnce();
    // Đổi ngẫu nhiên chu kỳ lần chớp tiếp theo (3.2-5.5s) để trông tự nhiên,
    // không đều tăm tắp như máy.
    uint32_t next_ms = 3200 + (esp_random() % 2300);
    lv_timer_set_period(timer, next_ms);
}

void OledDisplay::SetEmotion(const char* emotion) {
    if (eyes_area_ != nullptr) {
        DisplayLockGuard lock(this);
        SetEyeEmotion_128x64(emotion);
        return;
    }
    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    const char* utf8 = noto_emoji_get_utf8(emotion);
    const lv_font_t* emotion_font = lvgl_theme->emoji_font()->font();
    if (utf8 == nullptr) {
        utf8 = material_symbols_get_utf8(emotion);
        emotion_font = lvgl_theme->large_icon_font()->font();
    }
    DisplayLockGuard lock(this);
    if (emotion_label_ == nullptr) {
        return;
    }
    if (utf8 != nullptr) {
        lv_obj_set_style_text_font(emotion_label_, emotion_font, 0);
        lv_label_set_text(emotion_label_, utf8);
    } else {
        lv_obj_set_style_text_font(emotion_label_, lvgl_theme->emoji_font()->font(), 0);
        lv_label_set_text(emotion_label_, NOTO_EMOJI_NEUTRAL);
    }
}

void OledDisplay::SetTheme(Theme* theme) {
    DisplayLockGuard lock(this);

    auto lvgl_theme = static_cast<LvglTheme*>(theme);
    auto text_font = lvgl_theme->text_font()->font();

    auto screen = lv_screen_active();
    lv_obj_set_style_text_font(screen, text_font, 0);
}

void OledDisplay::SetPowerSaveMode(bool on) {
    if (panel_) {
        Settings settings("wifi", false);
        if (settings.GetBool("power_save_display_off", false)) {
            esp_lcd_panel_disp_on_off(panel_, !on);
        }
    }
    LvglDisplay::SetPowerSaveMode(on);
}

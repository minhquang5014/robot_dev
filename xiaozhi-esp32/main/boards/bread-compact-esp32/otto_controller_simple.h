#ifndef __OTTO_CONTROLLER_SIMPLE_H__
#define __OTTO_CONTROLLER_SIMPLE_H__

#include "mcp_server.h"
#include "otto_movements.h"

#include <driver/gpio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>

// Cầu nối giữa AI (gọi qua MCP, giống self.lamp.turn_on) và 4 servo chân.
// Robot này chỉ có 4 servo chân (không tay), nên Init() truyền left_hand/
// right_hand = -1 (giá trị mặc định) để Otto tự biết has_hands_ = false.
//
// Các động tác chép từ test/servo_test/servo_test.ino — biên độ, lệch pha,
// chu kỳ ở đó đã đo trên mô hình 3D (3D-print/viewer.html) và chạy thử trên
// robot thật, nên giữ nguyên số. Dùng hàm Oscillate() riêng thay cho
// Otto::OscillateServos(): bản kia giữ pha của lần gọi trước nên lệch nhịp, và
// không đưa chân vào tư thế t=0 trước — servo bị quăng 25-35 độ ở nhịp đầu.
//
// Mỗi hành động chạy trong 1 task FreeRTOS riêng, không chặn task chính (âm
// thanh/mạng vẫn chạy bình thường trong lúc robot đang đi).
class OttoController {
public:
    OttoController(gpio_num_t left_leg, gpio_num_t right_leg, gpio_num_t left_foot,
                   gpio_num_t right_foot) {
        otto_.Init(left_leg, right_leg, left_foot, right_foot);  // Init() đã AttachServos()
        otto_.SetRestState(false);

        auto& mcp_server = McpServer::GetInstance();
        mcp_server.AddTool(
            "self.otto.action",
            "Điều khiển robot 2 chân. action: walk (đi, direction 1 tới / -1 lui), turn "
            "(quay, 1 trái / -1 phải), step (nhích một bước nhỏ, 1 tới / -1 lui), pivot "
            "(xoay nhích, 1 trái / -1 phải), jump (nhảy), dance (cả bài nhảy), celebrate "
            "(ăn mừng, giậm chân lắc lư), tiptoe (kiễng chân giữ dáng), sway (kiễng chân "
            "lắc lư), windup (lấy đà rồi đẩy), home (đứng thẳng). Chỉ gọi khi người dùng "
            "YÊU CẦU robot di chuyển, không tự ý gọi.",
            PropertyList({
                Property("action", kPropertyTypeString, "home"),
                Property("direction", kPropertyTypeInteger, 1, -1, 1),
            }),
            [this](const PropertyList& properties) -> ReturnValue {
                std::string action = properties["action"].value<std::string>();
                int dir = properties["direction"].value<int>() < 0 ? -1 : 1;
                if (!StartAction(action, dir)) {
                    return "Lỗi: action không hợp lệ. Dùng: walk, turn, step, pivot, jump, "
                           "dance, celebrate, tiptoe, sway, windup, home";
                }
                return true;
            });
    }

private:
    static constexpr int kFootLift = 5;   // lệch tâm cổ chân — nút quyết định độ nhấc chân
    static constexpr int kRefreshMs = 20;

    Otto otto_;
    bool busy_ = false;
    int pose_[SERVO_COUNT] = {90, 90, 90, 90, 90, 90};

    enum ActionType {
        kWalk, kTurn, kStep, kPivot, kJump, kDance, kCelebrate, kTiptoe, kSway, kWindup, kHome
    };
    struct ActionContext {
        OttoController* self;
        ActionType type;
        int dir;
    };

    bool StartAction(const std::string& action, int dir) {
        static const struct {
            const char* name;
            ActionType type;
        } kActions[] = {
            {"walk", kWalk},   {"turn", kTurn},           {"step", kStep},
            {"pivot", kPivot}, {"jump", kJump},           {"dance", kDance},
            {"celebrate", kCelebrate}, {"tiptoe", kTiptoe}, {"sway", kSway},
            {"windup", kWindup}, {"home", kHome},
        };
        const ActionType* type = nullptr;
        for (const auto& a : kActions) {
            if (action == a.name) {
                type = &a.type;
                break;
            }
        }
        if (type == nullptr) {
            return false;
        }
        if (busy_) {
            return true;  // bỏ qua lệnh mới, đánh hết lệnh đang chạy
        }
        auto* ctx = new ActionContext{this, *type, dir};
        busy_ = true;
        xTaskCreate(&OttoController::RunAction, "otto_action", 4096, ctx, 5, nullptr);
        return true;
    }

    // ---- hai viên gạch, giống moveServos() / oscillate() của sketch ----

    void Move(int ms, const int (&target)[4]) {
        int t[SERVO_COUNT] = {target[0], target[1], target[2], target[3], 90, 90};
        otto_.MoveServos(ms, t);
        std::copy(t, t + SERVO_COUNT, pose_);
    }

    // góc = 90 + O + A*sin(2π t/period + pha). Đặt chân vào tư thế t=0 trước.
    void Oscillate(const int (&A)[4], const int (&O)[4], const int (&ph)[4], int period,
                   float cycles) {
        int t0[4];
        int jump = 0;
        for (int i = 0; i < 4; i++) {
            t0[i] = 90 + O[i] + (int)std::lround(A[i] * std::sin(ph[i] * M_PI / 180.0));
            jump = std::max(jump, std::abs(t0[i] - pose_[i]));
        }
        if (jump > 2) {
            Move(std::clamp(200 + jump * 6, 200, 500), t0);
        }
        const int64_t start = esp_timer_get_time();
        const int64_t total = (int64_t)(period * cycles) * 1000;
        int64_t now;
        while ((now = esp_timer_get_time() - start) < total) {
            double w = 2.0 * M_PI * (double)now / 1000.0 / period;
            int p[4];
            for (int i = 0; i < 4; i++) {
                p[i] = 90 + O[i] + (int)std::lround(A[i] * std::sin(w + ph[i] * M_PI / 180.0));
            }
            Move(0, p);
            vTaskDelay(pdMS_TO_TICKS(kRefreshMs));
        }
    }

    void Home() { Move(500, {90, 90, 90, 90}); }

    // ---- động tác (servo_test.ino) ----

    // dir 1 = tới. Lệch pha cổ chân -90*dir: bàn chân dồn trọng lượng sang chân trụ
    // đúng lúc hông đưa chân kia ra trước; đổi dấu thì đi lùi.
    void Walk(int dir) {
        Oscillate({30, 30, 30, 30}, {0, 0, kFootLift, -kFootLift}, {0, 0, -90 * dir, -90 * dir},
                  1000, 4);
    }

    // Hông bên kia xoay NGƯỢC -10 thay vì đứng yên: đo trên mô hình 3D xoay 311° /
    // trượt ngang 25mm, so với bản Otto cũ 158° / 113mm. dir 1 = trái.
    void Turn(int dir) {
        int A[4] = {30, 30, 30, 30};
        A[dir > 0 ? LEFT_LEG : RIGHT_LEG] = -10;
        Oscillate({A[0], A[1], A[2], A[3]}, {0, 0, kFootLift, -kFootLift}, {0, 0, -90, -90},
                  1000, 4);
    }

    // Nhích bước nhỏ kiểu EMO: hông 8 ~ 14mm mỗi chu kỳ.
    void Step(int dir) {
        Oscillate({8, 8, 30, 30}, {0, 0, kFootLift, -kFootLift}, {0, 0, dir * 90, dir * 90}, 900,
                  2);
    }

    // Xoay nhích: hông 5 / -2 ~ 14 độ mỗi chu kỳ. dir 1 = trái.
    void Pivot(int dir) {
        int A[4] = {5, 5, 30, 30};
        A[dir > 0 ? LEFT_LEG : RIGHT_LEG] = -2;
        Oscillate({A[0], A[1], A[2], A[3]}, {0, 0, kFootLift, -kFootLift}, {0, 0, -90, -90},
                  1100, 2);
    }

    void Jump(int period = 1000) {
        Move(period / 2, {90, 90, 150, 30});
        Move(period / 2, {90, 90, 90, 90});
    }

    // Lấy đà: ngả chậm về một bên rồi bật ngược lại nhanh gấp ba.
    void Windup(int lean = 35) {
        Move(600, {90, 90, 90 + lean, 90 - lean});
        vTaskDelay(pdMS_TO_TICKS(250));
        Move(170, {90, 90, 90 - lean, 90 + lean});
        vTaskDelay(pdMS_TO_TICKS(200));
        Move(400, {90, 90, 90, 90});
    }

    // Ăn mừng: hai cổ chân CÙNG pha -> thân lắc, hai bàn chân thay nhau nhấc (giậm chân).
    void Celebrate() { Oscillate({12, -12, 22, 22}, {0, 0, 0, 0}, {0, 0, 0, 0}, 620, 4); }

    // Kiễng chân giữ dáng: cổ chân 50/130 (đo trên máy thật), giữ một nhịp rồi hạ.
    void TiptoeHold(int lean = 40, int reps = 2) {
        for (int k = 0; k < reps; k++) {
            Move(450, {90, 90, 90 - lean, 90 + lean});
            vTaskDelay(pdMS_TO_TICKS(400));
            Move(450, {90, 90, 90, 90});
            if (k < reps - 1) vTaskDelay(pdMS_TO_TICKS(200));
        }
    }

    void Sway() { Oscillate({0, 0, 20, 20}, {0, 0, 20, -20}, {0, 0, 0, 0}, 1000, 3); }

    // Cả bài: vào bài -> điệp khúc A -> ngó nghiêng B -> A nhanh hơn -> lấy đà ->
    // nhảy -> chốt dáng kiễng chân. Không Home() giữa các đoạn để liền mạch.
    void Dance() {
        const int kBeat = 480;
        for (int i = 0; i < 2; i++) {
            Move(190, {90, 90, 72, 108});
            Move(190, {90, 90, 90, 90});
        }
        vTaskDelay(pdMS_TO_TICKS(kBeat / 2));
        Oscillate({10, -10, 22, 22}, {0, 0, 0, 0}, {0, 0, 0, 0}, kBeat * 2, 4);
        vTaskDelay(pdMS_TO_TICKS(kBeat / 2));
        Oscillate({7, -2, 26, 26}, {0, 0, kFootLift, -kFootLift}, {0, 0, -90, -90}, kBeat * 2, 1);
        Oscillate({-2, 7, 26, 26}, {0, 0, kFootLift, -kFootLift}, {0, 0, -90, -90}, kBeat * 2, 1);
        vTaskDelay(pdMS_TO_TICKS(kBeat / 2));
        Oscillate({14, -14, 26, 26}, {0, 0, 0, 0}, {0, 0, 0, 0}, (int)(kBeat * 1.4), 4);
        Move(520, {90, 90, 122, 58});
        vTaskDelay(pdMS_TO_TICKS(220));
        Move(150, {90, 90, 58, 122});
        vTaskDelay(pdMS_TO_TICKS(120));
        Jump();
        Move(380, {90, 90, 50, 130});
        vTaskDelay(pdMS_TO_TICKS(1100));
    }

    static void RunAction(void* arg) {
        auto* ctx = static_cast<ActionContext*>(arg);
        auto* self = ctx->self;
        switch (ctx->type) {
            case kWalk: self->Walk(ctx->dir); break;
            case kTurn: self->Turn(ctx->dir); break;
            case kStep: self->Step(ctx->dir); break;
            case kPivot: self->Pivot(ctx->dir); break;
            case kJump: self->Jump(); break;
            case kDance: self->Dance(); break;
            case kCelebrate: self->Celebrate(); break;
            case kTiptoe: self->TiptoeHold(); break;
            case kSway: self->Sway(); break;
            case kWindup: self->Windup(); break;
            case kHome: break;  // Home() gọi bên dưới
        }
        self->Home();
        self->busy_ = false;
        delete ctx;
        vTaskDelete(nullptr);
    }
};

#endif  // __OTTO_CONTROLLER_SIMPLE_H__

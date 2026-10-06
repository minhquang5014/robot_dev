#ifndef __OTTO_CONTROLLER_SIMPLE_H__
#define __OTTO_CONTROLLER_SIMPLE_H__

#include "mcp_server.h"
#include "otto_movements.h"

#include <driver/gpio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// Cầu nối giữa AI (gọi qua MCP, giống self.lamp.turn_on) và code đi lại có
// sẵn trong otto_movements.cc (copy nguyên từ board otto-robot, không sửa).
// Robot này chỉ có 4 servo chân (không tay), nên Init() truyền left_hand/
// right_hand = -1 (giá trị mặc định) để Otto tự biết has_hands_ = false.
//
// Mỗi hành động chạy trong 1 task FreeRTOS riêng, không chặn task chính (âm
// thanh/mạng vẫn chạy bình thường trong lúc robot đang đi).
class OttoController {
public:
    OttoController(gpio_num_t left_leg, gpio_num_t right_leg, gpio_num_t left_foot,
                   gpio_num_t right_foot) {
        otto_.Init(left_leg, right_leg, left_foot, right_foot);
        otto_.AttachServos();
        otto_.SetRestState(false);

        auto& mcp_server = McpServer::GetInstance();
        mcp_server.AddTool(
            "self.otto.action",
            "Điều khiển robot 2 chân di chuyển. action: walk (đi tới/lui), turn (quay trái/"
            "phải), jump (nhảy), tiptoe (kiễng chân lắc lư), home (đứng thẳng/dừng lại). "
            "direction: 1 = tới/trái, -1 = lui/phải (chỉ dùng cho walk/turn). Chỉ gọi khi "
            "người dùng YÊU CẦU robot di chuyển, không tự ý gọi.",
            PropertyList({
                Property("action", kPropertyTypeString, "home"),
                Property("direction", kPropertyTypeInteger, 1, -1, 1),
            }),
            [this](const PropertyList& properties) -> ReturnValue {
                std::string action = properties["action"].value<std::string>();
                int dir = properties["direction"].value<int>();
                if (!StartAction(action, dir)) {
                    return "Lỗi: action không hợp lệ. Dùng: walk, turn, jump, tiptoe, home";
                }
                return true;
            });
    }

private:
    Otto otto_;
    bool busy_ = false;

    bool StartAction(const std::string& action, int dir) {
        if (busy_) {
            return true;  // bo qua lenh moi, danh het lenh dang chay
        }
        ActionType type;
        if (action == "walk") {
            type = kActionWalk;
        } else if (action == "turn") {
            type = kActionTurn;
        } else if (action == "jump") {
            type = kActionJump;
        } else if (action == "tiptoe") {
            type = kActionTiptoe;
        } else if (action == "home") {
            type = kActionHome;
        } else {
            return false;
        }

        auto* ctx = new ActionContext{this, type, dir};
        busy_ = true;
        xTaskCreate(&OttoController::RunAction, "otto_action", 4096, ctx, 5, nullptr);
        return true;
    }

    enum ActionType { kActionWalk, kActionTurn, kActionJump, kActionTiptoe, kActionHome };
    struct ActionContext {
        OttoController* self;
        ActionType type;
        int dir;
    };

    static void RunAction(void* arg) {
        auto* ctx = static_cast<ActionContext*>(arg);
        auto* self = ctx->self;
        switch (ctx->type) {
            case kActionWalk:
                self->otto_.Walk(4, 1000, ctx->dir);
                break;
            case kActionTurn:
                self->otto_.Turn(4, 2000, ctx->dir);
                break;
            case kActionJump:
                self->otto_.Jump(1, 1500);
                break;
            case kActionTiptoe:
                self->otto_.TiptoeSwing(3, 900, 15);
                break;
            case kActionHome:
                break;  // home() goi ben duoi, dung rieng switch de code gon
        }
        self->otto_.Home();
        self->busy_ = false;
        delete ctx;
        vTaskDelete(nullptr);
    }
};

#endif  // __OTTO_CONTROLLER_SIMPLE_H__

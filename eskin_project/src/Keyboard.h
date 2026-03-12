#ifndef KEYBOARD_H
#define KEYBOARD_H

#include <Wire.h>
#include <src/keyboardinput/matrix_keyboard.h>

class Keyboard {
public:
    Keyboard(TwoWire &wire = Wire, uint8_t i2cAddr = emakefun::MatrixKeyboard::kDefaultI2cAddress);
    bool begin();                     // 初始化 I2C 和键盘
    void tick();                      // 更新按键状态（需周期性调用）
    void processKeys() const;         // 检测按键并打印消息
    void tickAndProcess() { tick(); processKeys(); }  // 一键完成更新+处理
    bool isPressed(emakefun::MatrixKeyboard::Key key) const;

private:
    TwoWire &_wire;
    uint8_t _i2cAddr;
    emakefun::MatrixKeyboard _keyboard;
    bool _initialized;
};

extern Keyboard keyboard;  

#endif
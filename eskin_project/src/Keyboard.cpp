#include "Keyboard.h"

#if defined(ESP32)
constexpr gpio_num_t kI2cPinSda = GPIO_NUM_21;
constexpr gpio_num_t kI2cPinScl = GPIO_NUM_22;
#endif

Keyboard::Keyboard(TwoWire &wire, uint8_t i2cAddr)
    : _wire(wire), _i2cAddr(i2cAddr), _keyboard(wire, i2cAddr), _initialized(false) {}

bool Keyboard::begin() {
#if defined(ESP32)
    _wire.begin(kI2cPinSda, kI2cPinScl);
#else
    _wire.begin();
#endif
    auto result = _keyboard.Initialize();
    _initialized = (result == emakefun::MatrixKeyboard::ErrorCode::kOK);
    return _initialized;
}

void Keyboard::tick() {
    if (_initialized) {
        _keyboard.Tick();
    }
}

Keyboard keyboard;  

void Keyboard::processKeys() const {
    if (!_initialized) return;

    if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey1)) {
        Serial.println(F("key 1 pressed"));
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey2)) {
        Serial.println(F("key 2 pressed"));
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey3)) {
        Serial.println(F("key 3 pressed"));
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey4)) {
        Serial.println(F("key 4 pressed"));
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey5)) {
        Serial.println(F("key 5 pressed"));
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey6)) {
        Serial.println(F("key 6 pressed"));
    }
    // kKey1 无处理，保持原样
}

bool Keyboard::isPressed(emakefun::MatrixKeyboard::Key key) const {
    return _initialized && _keyboard.Pressed(key);
}
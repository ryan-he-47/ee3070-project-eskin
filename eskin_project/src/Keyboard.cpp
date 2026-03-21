#include "Keyboard.h"

#include "config.h"
extern PressToMIDI pressToMIDI;   


#if defined(ESP32)
constexpr gpio_num_t kI2cPinSda = GPIO_NUM_7;
constexpr gpio_num_t kI2cPinScl = GPIO_NUM_8;
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

    int newConfig = -1;

    if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey1)) {
        newConfig = 0;
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey2)) {
        newConfig = 1;
    } else if (_keyboard.Pressed(emakefun::MatrixKeyboard::kKey3)) {
        newConfig = 2;
    }
    // 可继续添加更多按键映射

    if (newConfig != -1 && newConfig != currentConfig) {
        currentConfig = newConfig;
        pressToMIDI.setConfig(configs[currentConfig]);
        Serial.printf("Switched to config %d\n", currentConfig);
    }
}

bool Keyboard::isPressed(emakefun::MatrixKeyboard::Key key) const {
    return _initialized && _keyboard.Pressed(key);
}
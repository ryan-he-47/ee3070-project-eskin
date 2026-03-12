#include "matrix_keyboard.h"

namespace emakefun {

MatrixKeyboard::MatrixKeyboard(TwoWire& wire, const uint8_t i2c_address) : wire_(wire), i2c_address_(i2c_address), key_(kKeyNone) {
}

MatrixKeyboard::ErrorCode MatrixKeyboard::Initialize() {
  ErrorCode result = ErrorCode::kUnknownError;
  for (uint8_t i = 0; i < 5; i++) {
    wire_.beginTransmission(i2c_address_);
    result = static_cast<ErrorCode>(wire_.endTransmission());
    if (result == ErrorCode::kOK) {
      return result;
    }
  }
  return result;
}

void MatrixKeyboard::Tick() {
  last_key_ = key_();
  key_ = ReadKey();
}

bool MatrixKeyboard::Pressed(const MatrixKeyboard::Key key) const {
  return (last_key_ & key) == 0 && (key_() & key) != 0;
}

bool MatrixKeyboard::Pressing(const MatrixKeyboard::Key key) const {
  return (last_key_ & key) != 0 && (key_() & key) != 0;
}

bool MatrixKeyboard::Released(const MatrixKeyboard::Key key) const {
  return (last_key_ & key) != 0 && (key_() & key) == 0;
}

bool MatrixKeyboard::Idle(const MatrixKeyboard::Key key) const {
  return (last_key_ & key) == 0 && (key_() & key) == 0;
}

MatrixKeyboard::KeyState MatrixKeyboard::GetKeyState(const Key key) const {
  if (Pressed(key)) {
    return KeyState::kKeyStatePressed;
  } else if (Pressing(key)) {
    return KeyState::kKeyStatePressing;
  } else if (Released(key)) {
    return KeyState::kKeyStateReleased;
  }

  return KeyState::kKeyStateIdle;
}

char MatrixKeyboard::GetCurrentPressedKey() const {
  static constexpr struct {
    Key key;
    char value;
  } key_value_map[] = {{kKey1, '1'},
                       {kKey2, '2'},
                       {kKey3, '3'},
                       {kKey4, '4'},
                       {kKey5, '5'},
                       {kKey6, '6'},
                       {kKey7, '7'},
                       {kKey8, '8'},
                       {kKey9, '9'},
                       {kKey0, '0'},
                       {kKeyA, 'A'},
                       {kKeyB, 'B'},
                       {kKeyC, 'C'},
                       {kKeyD, 'D'},
                       {kKeyAsterisk, '*'},
                       {kKeyNumberSign, '#'}};

  for (const auto& key_map : key_value_map) {
    if ((last_key_ & key_map.key) == 0 && (key_() & key_map.key) != 0) {
      return key_map.value;
    }
  }

  return '\0';
}

MatrixKeyboard::Key MatrixKeyboard::ReadKey() {
  Key key = kKeyNone;

  if (sizeof(key) != wire_.requestFrom(i2c_address_, sizeof(key))) {
    return key;
  }

  if (sizeof(key) != wire_.readBytes(reinterpret_cast<uint8_t*>(&key), sizeof(key))) {
    return key;
  }

  return key;
}
}  // namespace emakefun
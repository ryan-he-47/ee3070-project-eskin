#pragma once

#ifndef _EMAKEFUN_MATRIX_KEY_BOARD_H_
#define _EMAKEFUN_MATRIX_KEY_BOARD_H_

#include <Wire.h>
#include <stdint.h>

#include "debouncer.h"

/**
 * @file matrix_keyboard.h
 */

namespace emakefun {

/**
 * @~Chinese
 * @class MatrixKeyboard
 * @brief MatrixKeyboard是用于矩阵键盘模块的驱动类。
 */
/**
 * @~English
 * @class MatrixKeyboard
 * @brief MatrixKeyboard is a driver class for the Matrix Keyboard module.
 */
class MatrixKeyboard {
 public:
  /**
   * @~Chinese
   * @brief 默认I2C地址。
   */
  /**
   * @~English
   * @brief Default I2C address.
   */
  static constexpr uint8_t kDefaultI2cAddress = 0x65;

  /**
   * @~Chinese
   * @enum ErrorCode
   * @brief 错误码。
   */
  /**
   * @~English
   * @enum ErrorCode
   * @brief Error codes.
   */
  enum class ErrorCode : uint32_t {
    /**
     * @~Chinese
     * @brief 成功。
     */
    /**
     * @~English
     * @brief Success.
     */
    kOK = 0,
    /**
     * @~Chinese
     * @brief I2C数据太长，无法装入传输缓冲区。
     */
    /**
     * @~English
     * @brief I2C data too long to fit in transmit buffer.
     */
    kI2cDataTooLongToFitInTransmitBuffer = 1,
    /**
     * @~Chinese
     * @brief 在I2C发送地址时收到NACK。
     */
    /**
     * @~English
     * @brief NACK received on I2C transmit of address.
     */
    kI2cReceivedNackOnTransmitOfAddress = 2,
    /**
     * @~Chinese
     * @brief 在I2C发送数据时收到NACK。
     */
    /**
     * @~English
     * @brief NACK received on I2C transmit of data.
     */
    kI2cReceivedNackOnTransmitOfData = 3,
    /**
     * @~Chinese
     * @brief 其他I2C错误。
     */
    /**
     * @~English
     * @brief Other I2C errors.
     */
    kI2cOtherError = 4,
    /**
     * @~Chinese
     * @brief I2C通讯超时。
     */
    /**
     * @~English
     * @brief I2C communication timed out.
     */
    kI2cTimeout = 5,
    /**
     * @~Chinese
     * @brief 参数错误。
     */
    /**
     * @~English
     * @brief Invalid parameter.
     */
    kInvalidParameter = 6,
    /**
     * @~Chinese
     * @brief 未知错误。
     */
    /**
     * @~English
     * @brief Unknown error.
     */
    kUnknownError = 7,
  };

  /**
   *  @~Chinese
   * @enum Key
   * @brief 键值。
   */
  /**
   *  @~English
   * @enum Key
   * @brief Key values.
   */
  enum Key : uint16_t {
    /**
     * @~Chinese
     * @brief 无按键。
     */
    /**
     * @~English
     * @brief No Key.
     */
    kKeyNone = static_cast<Key>(0),
    /**
     * @~Chinese
     * @brief 按键0。
     */
    /**
     * @~English
     * @brief Key 0.
     */
    kKey0 = static_cast<Key>(1) << 7,
    /**
     * @~Chinese
     * @brief 按键1。
     */
    /**
     * @~English
     * @brief Key 1.
     */
    kKey1 = static_cast<Key>(1) << 0,
    /**
     * @~Chinese
     * @brief 按键2。
     */
    /**
     * @~English
     * @brief Key 2.
     */
    kKey2 = static_cast<Key>(1) << 4,
    /**
     * @~Chinese
     * @brief 按键3。
     */
    /**
     * @~English
     * @brief Key 3.
     */
    kKey3 = static_cast<Key>(1) << 8,
    /**
     * @~Chinese
     * @brief 按键4。
     */
    /**
     * @~English
     * @brief Key 4.
     */
    kKey4 = static_cast<Key>(1) << 1,
    /**
     * @~Chinese
     * @brief 按键5。
     */
    /**
     * @~English
     * @brief Key 5.
     */
    kKey5 = static_cast<Key>(1) << 5,
    /**
     * @~Chinese
     * @brief 按键6。
     */
    /**
     * @~English
     * @brief Key 6.
     */
    kKey6 = static_cast<Key>(1) << 9,
    /**
     * @~Chinese
     * @brief 按键7。
     */
    /**
     * @~English
     * @brief Key 7.
     */
    kKey7 = static_cast<Key>(1) << 2,
    /**
     * @~Chinese
     * @brief 按键8。
     */
    /**
     * @~English
     * @brief Key 8.
     */
    kKey8 = static_cast<Key>(1) << 6,
    /**
     * @~Chinese
     * @brief 按键9。
     */
    /**
     * @~English
     * @brief Key 9.
     */
    kKey9 = static_cast<Key>(1) << 10,
    /**
     * @~Chinese
     * @brief 按键A。
     */
    /**
     * @~English
     * @brief Key A.
     */
    kKeyA = static_cast<Key>(1) << 12,
    /**
     * @~Chinese
     * @brief 按键B。
     */
    /**
     * @~English
     * @brief Key B.
     */
    kKeyB = static_cast<Key>(1) << 13,
    /**
     * @~Chinese
     * @brief 按键C。
     */
    /**
     * @~English
     * @brief Key C.
     */
    kKeyC = static_cast<Key>(1) << 14,
    /**
     * @~Chinese
     * @brief 按键D。
     */
    /**
     * @~English
     * @brief Key D.
     */
    kKeyD = static_cast<Key>(1) << 15,
    /**
     * @~Chinese
     * @brief 按键星号。
     */
    /**
     * @~English
     * @brief Key asterisk.
     */
    kKeyAsterisk = static_cast<Key>(1) << 3,
    /**
     * @~Chinese
     * @brief 按键井号。
     */
    /**
     * @~English
     * @brief Key number sign.
     */
    kKeyNumberSign = static_cast<Key>(1) << 11,
  };

  /**
   * @~Chinese
   * @enum KeyState
   * @brief 按键状态。
   */
  /**
   * @~English
   * @enum KeyState
   * @brief Key state.
   */
  enum class KeyState : uint8_t {
    /**
     * @~Chinese
     * @brief 按键空闲。
     */
    /**
     * @~English
     * @brief Key is idle.
     */
    kKeyStateIdle,
    /**
     * @~Chinese
     * @brief 按键被按下。
     */
    /**
     * @~English
     * @brief Key is pressed.
     */
    kKeyStatePressed,
    /**
     * @~Chinese
     * @brief 按键被按住。
     */
    /**
     * @~English
     * @brief Key is pressing.
     */
    kKeyStatePressing,
    /**
     * @~Chinese
     * @brief 按键被弹起。
     */
    /**
     * @~English
     * @brief Key is released.
     */
    kKeyStateReleased,
  };

  /**
   * @~Chinese
   * @brief 构造函数
   * @param[in] wire TwoWire 对象引用。
   * @param[in] i2c_address I2C地址。
   */
  /**
   * @~English
   * @brief 构造函数
   * @param[in] wire TwoWire object reference.
   * @param[in] i2c_address I2C address.
   */
  explicit MatrixKeyboard(TwoWire& wire, const uint8_t i2c_address);

  /**
   * @~Chinese
   * @brief 初始化。
   * @return 返回值请参考 @ref ErrorCode。
   */
  /**
   * @~English
   * @brief Initialize.
   * @return Return value refer to @ref ErrorCode.
   */
  ErrorCode Initialize();

  /**
   * @~Chinese
   * @brief 扫描按键，在函数loop中调用，每次循环先调用该函数再查询按键状态。
   */
  /**
   * @~English
   * @brief Scan keys, call this function in the loop function, and then query the key state each time the loop is executed.
   */
  void Tick();

  /**
   * @~Chinese
   * @brief 查询按键是否被按下。
   * @param[in] key 按键，参考枚举 @ref Key。
   * @return 返回true代表按键被按下。
   */
  /**
   * @~English
   * @brief Check whether the button is pressed.
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return Returning true indicates that the button has been pressed.
   */
  bool Pressed(const Key key) const;

  /**
   * @~Chinese
   * @brief 查询按键是否被按住。
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return 返回true代表按键被按住。
   */
  /**
   * @~English
   * @brief Check whether the key is held down.
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return Return true to indicate that the key is held down.
   */
  bool Pressing(const Key key) const;

  /**
   * @~Chinese
   * @brief 查询按键是否被释放。
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return 返回true代表按键被释放。
   */
  /**
   * @~English
   * @brief Check whether the key has been released.
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return Returning true indicates that the key has been released.
   */
  bool Released(const Key key) const;

  /**
   * @~Chinese
   * @brief 查询按键是否空闲。
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return 返回true代表按键空闲。
   */
  /**
   * @~English
   * @brief Check whether the key is idle.
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return Return true to indicate that the key is idle.
   */
  bool Idle(const Key key) const;

  /**
   * @~Chinese
   * @brief 查询按键状态。
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return 按键状态，参考枚举 @ref KeyState。
   */
  /**
   * @~English
   * @brief Query key state.
   * @param[in] Key, refer to the enumeration @ref Key.
   * @return Key state, refer to enumeration @ref KeyState.
   */
  KeyState GetKeyState(const Key key) const;

  /**
   * @~Chinese
   * @brief 获取当前按下的按键。
   * @return char 按键字符：'0'-'9'、'A'-'D'、'*'、'#'，返回'\0'表示没有按键按下。
   * @note 如果多个按键同时按下，则按顺序返回第一个检测到的按键。
   */
  /**
   * @~English
   * @brief Get the currently pressed key.
   * @return char key character: '0'-'9', 'A'-'D', '*', '#', returns '\0' to indicate no key pressed.
   * @note If multiple buttons are pressed simultaneously, return to the first detected button in order.
   */
  char GetCurrentPressedKey() const;

 private:
  MatrixKeyboard(const MatrixKeyboard&) = delete;
  MatrixKeyboard& operator=(const MatrixKeyboard&) = delete;

  Key ReadKey();

  TwoWire& wire_ = Wire;
  const uint8_t i2c_address_ = kDefaultI2cAddress;
  Debouncer<Key> key_;
  Key last_key_ = kKeyNone;
};
}  // namespace emakefun
#endif
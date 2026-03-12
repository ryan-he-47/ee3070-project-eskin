#pragma once

#ifndef _EMAKEFUN_MATRIX_KEY_BOARD_LIB_H_
#define _EMAKEFUN_MATRIX_KEY_BOARD_LIB_H_

#include <WString.h>

/**
 * @file matrix_keyboard_lib.h
 */

namespace emakefun {
namespace matrix_keyboard_lib {

/**
 * @~Chinese
 * @brief 主版本号。
 */
/**
 * @~English
 * @brief Major version number.
 */
constexpr uint8_t kVersionMajor = 1;

/**
 * @~Chinese
 * @brief 次版本号。
 */
/**
 * @~English
 * @brief Minor version number.
 */
constexpr uint8_t kVersionMinor = 0;

/**
 * @~Chinese
 * @brief 修订版本号。
 */
/**
 * @~Englishs
 * @brief Patch version number.
 */
constexpr uint8_t kVersionPatch = 1;

/**
 * @~Chinese
 * @brief 获取版本号字符串。
 * @return 版本号字符串，格式为 major.minor.patch。
 */
/**
 * @~English
 * @brief Get the version number string.
 * @return The version number string in the format of major.minor.patch.
 */
String Version() {
  return String(kVersionMajor) + '.' + kVersionMinor + '.' + kVersionPatch;
}
}  // namespace matrix_keyboard_lib
}  // namespace emakefun
#endif
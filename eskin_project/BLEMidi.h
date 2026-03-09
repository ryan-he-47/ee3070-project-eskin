// ============================================================
//  BLEMidi.h
//  BLE MIDI 广播模块 —— 头文件
//
//  职责：
//    · 定义 BLE 设备名宏 BLE_MIDI_DEVICE_NAME
//    · 声明对外接口 bleMidiBegin() / bleMidiSendEvent()
//
//  依赖：
//    · Arduino BLE-MIDI 库 (lathoub/ESP32-BLE-MIDI)
//    · pressure_process.h  (MIDIEvent / MIDIEventType)
//
//  使用方式：
//    setup()  中调用 bleMidiBegin()
//    任务中   调用 bleMidiSendEvent(event)
// ============================================================

#ifndef BLE_MIDI_H
#define BLE_MIDI_H

#include <Arduino.h>
#include "pressure_process.h"   // MIDIEvent / MIDIEventType

// ── 宏定义：BLE 广播设备名称 ──────────────────────────────────
// 可在编译时通过 -D BLE_MIDI_DEVICE_NAME="xxx" 覆盖
#ifndef BLE_MIDI_DEVICE_NAME
  #define BLE_MIDI_DEVICE_NAME  "ESP32-MIDI"
#endif

// ── 公开接口声明 ──────────────────────────────────────────────

/**
 * @brief 初始化 BLE MIDI Server 并开始广播
 *        在 setup() 中调用一次
 * @param deviceName  BLE 广播名（默认 BLE_MIDI_DEVICE_NAME）
 */
void bleMidiBegin(const char* deviceName = BLE_MIDI_DEVICE_NAME);

/**
 * @brief 将 MIDIEvent 转化为 BLE MIDI 信号并广播
 *        在任务循环中调用
 * @param evt  来自 pressure_process 的 MIDIEvent 结构体
 */
void bleMidiSendEvent(const MIDIEvent& evt);

#endif // BLE_MIDI_H

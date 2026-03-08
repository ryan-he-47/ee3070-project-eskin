#ifndef BLE_MIDI_H
#define BLE_MIDI_H

// ============================================================
//  BLEMidi.h
//  BLE MIDI 广播模块：初始化与事件发送接口
//
//  依赖库：lathoub/ESP32-BLE-MIDI
//  使用方式：
//    setup() 中调用 bleMidiBegin()
//    发送时调用 bleMidiSendEvent(event)
// ============================================================

#include <Arduino.h>
#include "pressure_process.h"   // MIDIEvent / MIDIEventType 定义在此

// BLE 广播设备名称（可在编译时通过 build_flags 覆盖）
#ifndef BLE_MIDI_DEVICE_NAME
  #define BLE_MIDI_DEVICE_NAME  "ESP32-MIDI"
#endif

// ── 公开函数声明 ──────────────────────────────────────────────

// 初始化 BLE MIDI Server，并注册连接/断连回调（在 setup() 中调用）
void bleMidiBegin(const char* deviceName = BLE_MIDI_DEVICE_NAME);

// 将一个 MIDIEvent 转化为 BLE MIDI 信号并发送
void bleMidiSendEvent(const MIDIEvent& evt);

#endif // BLE_MIDI_H

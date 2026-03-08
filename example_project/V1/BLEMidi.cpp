// ============================================================
//  BLEMidi.cpp
//  实现：BLE MIDI Server 初始化 + MIDIEvent → BLE MIDI 发送
//
//  MIDIEvent 结构体来自 pressure_process.h：
//    type    : MIDIEventType（NoteOn/NoteOff/ControlChange/ProgramChange/PitchBend）
//    channel : MIDI 通道（1-16，字节层面转为 0-15）
//    data1   : 音符编号 / 控制器编号 / Pitch LSB
//    data2   : 力度 / 控制器值 / Pitch MSB
// ============================================================

#include "BLEMidi.h"
#include <lib/ESP32_Host_MIDI/src/BLEConnection.h>   // ESP32_Host_MIDI 库

// ─────────────────────────────────────────────────────────────
//  模块内部：BLEConnection 实例与初始化标志
// ─────────────────────────────────────────────────────────────

static BLEConnection _ble;
static bool          _bleInited = false;

// ─────────────────────────────────────────────────────────────
//  _bleMidiInit()  ——  懒初始化（首次发送时自动调用）
// ─────────────────────────────────────────────────────────────

static void _bleMidiInit(const char* deviceName) {
    if (_bleInited) return;
    _bleInited = true;
    _ble.begin(deviceName);
    Serial.printf("[BLE] MIDI Server 已启动，设备名: %s\n", deviceName);
}

// ─────────────────────────────────────────────────────────────
//  bleMidiBegin()  ——  显式初始化（可选，在 setup() 中调用）
// ─────────────────────────────────────────────────────────────

void bleMidiBegin(const char* deviceName) {
    _bleMidiInit(deviceName);
}

// ─────────────────────────────────────────────────────────────
//  bleMidiSendEvent()
//  将 pressure_process.h 中的 MIDIEvent 转化为原始 MIDI 字节
//  并通过 BLEConnection::sendMidiMessage() 封装成 BLE MIDI 1.0 包发出
// ─────────────────────────────────────────────────────────────

void bleMidiSendEvent(const MIDIEvent& evt) {
    _bleMidiInit(BLE_MIDI_DEVICE_NAME);   // 首次调用时自动初始化

    // MIDIEvent.channel 为 1-16，字节层面需 0-15
    uint8_t ch = static_cast<uint8_t>(evt.channel - 1) & 0x0F;

    switch (evt.type) {
        case MIDIEventType::NoteOn: {
            uint8_t raw[3] = { static_cast<uint8_t>(0x90 | ch), evt.data1, evt.data2 };
            _ble.sendMidiMessage(raw, 3);
            break;
        }
        case MIDIEventType::NoteOff: {
            uint8_t raw[3] = { static_cast<uint8_t>(0x80 | ch), evt.data1, evt.data2 };
            _ble.sendMidiMessage(raw, 3);
            break;
        }
        case MIDIEventType::ControlChange: {
            uint8_t raw[3] = { static_cast<uint8_t>(0xB0 | ch), evt.data1, evt.data2 };
            _ble.sendMidiMessage(raw, 3);
            break;
        }
        case MIDIEventType::ProgramChange: {
            uint8_t raw[2] = { static_cast<uint8_t>(0xC0 | ch), evt.data1 };
            _ble.sendMidiMessage(raw, 2);
            break;
        }
        case MIDIEventType::PitchBend: {
            // data1 = LSB (0-127), data2 = MSB (0-127)，合并为 14-bit
            uint8_t raw[3] = { static_cast<uint8_t>(0xE0 | ch), evt.data1, evt.data2 };
            _ble.sendMidiMessage(raw, 3);
            break;
        }
        default:
            break;
    }
}

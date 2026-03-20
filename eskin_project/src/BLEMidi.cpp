// ============================================================
//  BLEMidi.cpp
//  BLE MIDI 广播模块 —— 实现文件
//
//  职责：
//    · 使用 BLEMIDI_CREATE_INSTANCE 宏创建 BLE MIDI 传输层实例
//      和 MIDI 接口实例（全局单例）
//    · 实现 bleMidiBegin()     —— 初始化并启动广播
//    · 实现 bleMidiSendEvent() —— 将 MIDIEvent 转发为
//      MIDI.sendNoteOn / sendNoteOff / sendControlChange 等调用
//
//  依赖库（Arduino IDE 全局库，无需项目内 lib/ 路径）：
//    · FortySevenEffects/arduino-midi-library  (MIDI.h)
//    · lathoub/ESP32-BLE-MIDI                  (BLEMIDI_Transport.h)
//
//  BLEMIDI_CREATE_INSTANCE(DeviceName, Name) 宏展开等效于：
//    BLEMIDI_Transport<BLEMIDI_ESP32>  BLE##Name(DeviceName);
//    MidiInterface<BLEMIDI_Transport<BLEMIDI_ESP32>, MySettings>
//                                      Name((Transport&)BLE##Name);
// ============================================================

#include "BLEMidi.h"

// ── 包含 BLE-MIDI 库头文件（系统库路径，Arduino IDE 自动解析）──
#include <BLEMIDI_Transport.h>          // BLEMIDI_Transport<T> 模板 + BLEMIDI_CREATE_INSTANCE 宏
#include <hardware/BLEMIDI_ESP32.h>     // ESP32 BLE 硬件适配层 + BLEMIDI_ESP32 类

// ─────────────────────────────────────────────────────────────
//  全局 BLE MIDI 实例
//  BLEMIDI  : BLEMIDI_Transport<BLEMIDI_ESP32>  传输层对象
//  MIDI     : MidiInterface<...>                高层 MIDI 接口
//
//  注意：BLEMIDI_CREATE_INSTANCE 宏使用完整命名空间限定，
//        此处不需要 using namespace bleMidi
// ─────────────────────────────────────────────────────────────
BLEMIDI_CREATE_INSTANCE(BLE_MIDI_DEVICE_NAME, MIDI)

// ─────────────────────────────────────────────────────────────
//  bleMidiBegin()
//  · 注册连接 / 断连状态回调（串口调试输出）
//  · 调用 MIDI.begin() 启动 BLE MIDI Server 并开始广播
//  · 注：deviceName 参数在宏展开时已固定为 BLE_MIDI_DEVICE_NAME，
//    此处仅用于打印，若需动态修改设备名须在宏调用前修改宏定义
// ─────────────────────────────────────────────────────────────
void bleMidiBegin(const char* deviceName) {
    BLEMIDI.setHandleConnected([]() {
        Serial.println("[BLE MIDI] 已连接");
    });
    BLEMIDI.setHandleDisconnected([]() {
        Serial.println("[BLE MIDI] 已断开，重新广播中...");
    });

    // MIDI_CHANNEL_OMNI = 0，监听所有通道（发送时通道由 evt.channel 指定）
    MIDI.begin(MIDI_CHANNEL_OMNI);

    Serial.printf("[BLE MIDI] 广播已启动，设备名: %s\n", deviceName);
    Serial.println("[BLE MIDI] 请在 Mac「音频 MIDI 设置」中搜索并连接此设备");
}

// ─────────────────────────────────────────────────────────────
//  bleMidiSendEvent()
//  将 pressure_process.h 中定义的 MIDIEvent 结构体
//  转发至 BLEMIDI_Transport，通过 BLE MIDI 1.0 协议广播
//
//  MIDIEvent 字段：
//    type    : MIDIEventType 枚举（NoteOn/NoteOff/CC/PC/PitchBend）
//    channel : MIDI 通道，1-16（直接传入 MIDI.sendXxx，无需转换）
//    data1   : 音符编号 / 控制器编号 / PitchBend LSB
//    data2   : 力度 / 控制器值 / PitchBend MSB
// ─────────────────────────────────────────────────────────────
void bleMidiSendEvent(const MIDIEvent& evt) {
    if ((evt.type != MIDIEventType::NoteOn) and (evt.type != MIDIEventType::NoteOff)){
       // Serial.print("fuck");
    }
    switch (evt.type) {
        
        case MIDIEventType::NoteOn:
            // sendNoteOn(note, velocity, channel)
            MIDI.sendNoteOn(evt.data1, evt.data2, evt.channel);
            break;

        case MIDIEventType::NoteOff:
            // sendNoteOff(note, velocity, channel)
            MIDI.sendNoteOff(evt.data1, evt.data2, evt.channel);
            break;

        case MIDIEventType::ControlChange:
            // sendControlChange(controllerNumber, value, channel)
            MIDI.sendControlChange(evt.data1, evt.data2, evt.channel);
            break;

        case MIDIEventType::ProgramChange:
            // sendProgramChange(programNumber, channel)
            MIDI.sendProgramChange(evt.data1, evt.channel);
            break;

        case MIDIEventType::PitchBend: {
            // MIDI.h 的 sendPitchBend 接受有符号 -8192 ~ +8191
            // MIDIEvent 约定：data1 = 14-bit 值的低 7 位（LSB）
            //                 data2 = 14-bit 值的高 7 位（MSB）
            // 合并后减去中心值 8192 得到有符号偏移量
            int16_t bend = (int16_t)(((uint16_t)evt.data2 << 7) | evt.data1) - 8192;
            MIDI.sendPitchBend(bend, evt.channel);
            break;
        }

        default:
            break;
    }
}

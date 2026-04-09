// ============================================================
//  USBMidi.cpp
//  USB MIDI 传输模块 —— 实现文件
//
//  职责：
//    · 实例化底层 USBMIDI 对象
//    · 实现 usbMidiBegin()     —— 初始化原生 USB 硬件
//    · 实现 usbMidiSendEvent() —— 将 MIDIEvent 转发为 USB 指令
// ============================================================


#include "USBMIDI1.h"

#include "USB.h"
#include "USBMIDI.h"


// ─────────────────────────────────────────────────────────────
//  全局 USB MIDI 实例
// ─────────────────────────────────────────────────────────────
USBMIDI UsbMidi;

// ─────────────────────────────────────────────────────────────
//  usbMidiBegin()
//  启动原生 USB 控制器，并初始化 USB MIDI 实例
// ─────────────────────────────────────────────────────────────
void usbMidiBegin() {
    USB.begin();
    UsbMidi.begin();

}

// ─────────────────────────────────────────────────────────────
//  usbMidiSendEvent()
//  将 pressure_process.h 中定义的 MIDIEvent 结构体
//  转发至原生的 USBMIDI 库发送
// ─────────────────────────────────────────────────────────────
void usbMidiSendEvent(const MIDIEvent& evt) {
    switch (evt.type) {
        
        case MIDIEventType::NoteOn:
            UsbMidi.noteOn(evt.data1, evt.data2, evt.channel);

            break;

        case MIDIEventType::NoteOff:
            UsbMidi.noteOff(evt.data1, evt.data2, evt.channel);
            break;

        case MIDIEventType::ControlChange:
            UsbMidi.controlChange(evt.data1, evt.data2, evt.channel);
            break;

        case MIDIEventType::ProgramChange:
            UsbMidi.programChange(evt.data1, evt.channel);
            break;

        case MIDIEventType::PitchBend: {
            // 项目内部的 PitchBend 被拆分为两个 7-bit 数据
            // USB MIDI 库接受 0 ~ 16383 的 14-bit 无符号整数
            uint16_t bendValue = ((uint16_t)evt.data2 << 7) | evt.data1;
            UsbMidi.pitchBend(bendValue, evt.channel);
            break;
        }

        case MIDIEventType::ChannelAT:
            UsbMidi.channelPressure(evt.data1, evt.channel);
            break;

        
        case MIDIEventType::PolyAT://还没有验证，先注释掉
            UsbMidi.polyPressure(evt.data1, evt.channel);
            break;


        default:
            break;
    }
}
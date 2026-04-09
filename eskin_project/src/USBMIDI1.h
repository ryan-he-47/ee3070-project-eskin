// ============================================================
//  USBMidi.h
//  USB MIDI 传输模块 —— 头文件
//
//  职责：
//    · 声明对外接口 usbMidiBegin() / usbMidiSendEvent()
//    · 专为 ESP32-P4 原生 USB MIDI 设计
//
//  使用方式：
//    setup()  中调用 usbMidiBegin()
//    任务中   调用 usbMidiSendEvent(event)
// ============================================================

#ifndef USB_MIDI_H
#define USB_MIDI_H

#include <Arduino.h>
#include <cstddef>
#include "pressure_process.h" // MIDIEvent 结构体定义在这里

void usbMidiBegin();

void usbMidiSendEvent(const MIDIEvent& evt);

#endif // USB_MIDI_H
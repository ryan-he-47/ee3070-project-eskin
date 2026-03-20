#include <stdint.h>
#ifndef MIDI_TOOL_H
#define MIDI_TOOL_H
#include <Arduino.h>
#include <src/pressure_process.h>
#define MATRIX_ROWS 16  // 矩阵行数
#define MATRIX_COLS 16  // 矩阵列数
typedef uint8_t eskinMatrix[MATRIX_ROWS][MATRIX_COLS]; //定义16*16大小的unit8_t数组类，名叫eskinMatrix
struct MIDIEvent;
void debugSend(eskinMatrix* mat=nullptr, const String& msg="" );//向电脑发送调试信息，可以发送矩阵和字符串

void midiEventEncoder(const MIDIEvent& event,uint8_t midiFrame[3]);//把事件类型变为uint8_t数组

String midiEventToString(const MIDIEvent& event);//把midievent变成一串string


#endif
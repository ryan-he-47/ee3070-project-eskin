#include <stdint.h>
#include <Arduino.h>
#include "src/midi_tool.h"
#include "src/pressure_process.h" 

void debugSend(eskinMatrix* mat, const String& msg ){
  const uint8_t matrixHeader[4] = {0x00, 0x10, 0x11, 0x20};//矩阵帧头
  const uint8_t stringHeader[4] = {0x01, 0x02, 0x30, 0x22}; // 字符串帧头
  if(mat!=nullptr){
    Serial.write(matrixHeader, 4);//发送帧头
    Serial.write((uint8_t*)mat, sizeof(eskinMatrix)); // 发送压力矩阵
  }
  if(!msg.isEmpty()){
    uint16_t strLen = msg.length(); // 字符串长度（2字节
    // 1. 发送字符串帧头
    Serial.write(stringHeader, sizeof(stringHeader));
    // 2. 发送字符串长度（小端模式，与Python端匹配）
    Serial.write((uint8_t*)&strLen, sizeof(strLen));
    // 3. 发送字符串字节数据
    Serial.write(msg.c_str(), strLen);
  }
}

void midiEventEncoder(const MIDIEvent& event,uint8_t midiFrame[3]){
  // ========== 步骤1：参数合法性校验（避免非法MIDI数据） ==========
    // 1. 通道校验：MIDI规范通道是1-16，超出则默认1
    uint8_t validChannel = (event.channel >= 1 && event.channel <= 16) ? event.channel : 1;
    // 2. 数据1/2校验：MIDI数据字节必须是0-127（最高位为0）
    uint8_t validData1 = event.data1 & 0x7F; // 截断高1位，确保0-127
    uint8_t validData2 = event.data2 & 0x7F;

    // ========== 步骤2：计算MIDI状态字节 ==========
    // 状态字节 = 事件类型高4位 | 通道低4位（通道1→0，通道16→15）
    uint8_t eventTypeValue = static_cast<uint8_t>(event.type); // 枚举转uint8_t
    uint8_t statusByte = (eventTypeValue & 0xF0) | ((validChannel - 1) & 0x0F);

    // ========== 步骤3：填充3字节MIDI帧 ==========
    midiFrame[0] = statusByte; // 第1字节：状态字节
    midiFrame[1] = validData1; // 第2字节：数据1

    // 特殊处理：ProgramChange仅2字节，数据2补0；其他事件用validData2
    if (event.type == MIDIEventType::ProgramChange) {
        midiFrame[2] = 0;
    } else {
        midiFrame[2] = validData2;
    }
}


String getMidiEventTypeStr(MIDIEventType type) {
    switch(type) {
        case MIDIEventType::NoteOn: return        "NoteOn       ";
        case MIDIEventType::NoteOff: return       "NoteOff      ";
        case MIDIEventType::ControlChange: return "ControlChange";
        case MIDIEventType::ProgramChange: return "ProgramChange";
        case MIDIEventType::PitchBend: return     "PitchBend    ";
        default: return                           "Unknown      ";
    }
}
String midiEventToString(const MIDIEvent& event) {
    // 步骤1：MIDI数据合法性校验
    uint8_t validChannel = (event.channel >= 1 && event.channel <= 16) ? event.channel : 1;
    uint8_t validData1 = event.data1 & 0x7F;
    uint8_t validData2 = event.data2 & 0x7F;

    // 步骤2：计算3字节MIDI帧
    uint8_t eventTypeVal = static_cast<uint8_t>(event.type);
    uint8_t statusByte = (eventTypeVal & 0xF0) | ((validChannel - 1) & 0x0F);
    uint8_t data2Byte = (event.type == MIDIEventType::ProgramChange) ? 0 : validData2;

    // 步骤3：格式化字符串（状态字节16进制，数据位10进制）
    String readableStr = "";

    // 状态字节：两位十六进制 + 事件类型描述 + 通道
    readableStr += "状态字节: 0x";
    if (statusByte < 0x10) readableStr += "0"; // 补前导0
    readableStr += String(statusByte, HEX);
    readableStr += " (" + getMidiEventTypeStr(event.type) + ", 通道" + String(validChannel) + ") | ";

    // Data1：十进制 + 语义标注
    readableStr += "Data1: " + String(validData1);
    if (event.type == MIDIEventType::NoteOn || event.type == MIDIEventType::NoteOff) {
        readableStr += " (音高。。。)| ";
    } else if (event.type == MIDIEventType::ControlChange) {
        readableStr += " (控制器号。)| ";
    } else if (event.type == MIDIEventType::ProgramChange) {
        readableStr += " (程序号。。)| ";
    } else if (event.type == MIDIEventType::PitchBend) {
        readableStr += " (弯音低七位)| ";
    }else{
        readableStr += " (未定义。。)| ";
    }

    // Data2：十进制 + 语义标注
    readableStr += "Data2: " + String(data2Byte);
    if (event.type == MIDIEventType::NoteOn) {
        readableStr += " (力度。。。)";
    } else if (event.type == MIDIEventType::NoteOff) {
        readableStr += " (释放速度。)";
    } else if (event.type == MIDIEventType::ControlChange) {
        readableStr += " (控制器值。)";
    } else if (event.type == MIDIEventType::ProgramChange) {
        readableStr += " (保留值。。)";
    } else if (event.type == MIDIEventType::PitchBend) {
        readableStr += " (弯音高七位)";
    }else{
        readableStr += " (未定义。。)";
    }

    // 统一转为大写（十六进制字母）
    readableStr.toUpperCase();
    return readableStr;



}


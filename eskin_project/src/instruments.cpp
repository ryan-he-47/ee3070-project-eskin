#include <Arduino.h>
#include "src/pressure_process.h"

//====================以下实现多种按键逻辑======================================

void PressToMIDI::_basicInstrument(int row,int col,int channel){//这是能响就行基础款，不支持自定义键的音高
  QueueHandle_t output=_midiQueue;
  MIDIEvent event;
  static bool flagMap[16][16]={false};
  const int deadzone=10;

  event.channel=channel;
  event.data1=row+col+48;//middle C =60, 该映射可以覆盖低一个八度和高一个多八度
  event.data2=80;//能响就行
  if((_pressNow[row][col]>=(_usingConfig.trigThreshMap[row][col]+deadzone))&&!flagMap[row][col]){
    event.type=MIDIEventType::NoteOn;
    flagMap[row][col]=1;
    xQueueSendToBack(output, &event, 0);
  }else if((_pressNow[row][col]<(_usingConfig.trigThreshMap[row][col]))&&flagMap[row][col]){
    event.type=MIDIEventType::NoteOff;
    flagMap[row][col]=0;
    xQueueSendToBack(output, &event, 0);
  

  }
  
}















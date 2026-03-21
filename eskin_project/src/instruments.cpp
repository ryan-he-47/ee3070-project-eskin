#include <Arduino.h>
#include "src/pressure_process.h"

//====================以下实现多种按键逻辑======================================

void PressToMIDI::_basicInstrument(int row,int col,int channel){//这是能响就行基础款，不支持自定义键的音高
  QueueHandle_t output=_midiQueue;
  MIDIEvent event;
  static bool flagMap[16][16]={false};
  const int deadzone=2;

  event.channel=channel;
  event.data1=row+col+48;//middle C =60, 该映射可以覆盖低一个八度和高一个多八度
  event.data2=_pressNow[row][col];//能响就行
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





void PressToMIDI::_piano(int row,int col,int channel){//钢琴
  QueueHandle_t output=_midiQueue;
  MIDIEvent event;
  eskinMatrix* lastFrame=getCachePressPtr(1);
  if(lastFrame==nullptr){
    return;
  }
  const int deadzone=2;
  event.channel=channel;
  event.data1=_usingConfig.pitchMap[row][col];
  event.MPEnote=_usingConfig.pitchMap[row][col];
  int currentPressure=_pressNow[row][col]+_pressNow[row][col+1]+_pressNow[row+1][col]+_pressNow[row+1][col+1]-35*3;//4键平均压力
  int lastPressure=(*lastFrame)[row][col]+(*lastFrame)[row][col+1]+(*lastFrame)[row+1][col]+(*lastFrame)[row+1][col+1]-35*3;
  event.data2=currentPressure;

  if( (currentPressure>=(_usingConfig.trigThreshMap[row][col]+deadzone)) && (_KeyStateMap[row][col]==KeyState::FREE) ){
    _KeyStateMap[row][col]=KeyState::PRESSING;
  }
  
  
  if((currentPressure<lastPressure)&&(_KeyStateMap[row][col]==KeyState::PRESSING)){
      event.type=MIDIEventType::NoteOn;
      event.data2=lastPressure;
      _KeyStateMap[row][col]=KeyState::LIFTING;
      xQueueSendToBack(output, &event, 0);
    }
  
  
  
  
  if((currentPressure<(_usingConfig.trigThreshMap[row][col]))&&(_KeyStateMap[row][col]==KeyState::LIFTING)){
    event.type=MIDIEventType::NoteOff;
    event.data2=0;
    _KeyStateMap[row][col]=KeyState::FREE;
    xQueueSendToBack(output, &event, 0);
  

  }
  
}
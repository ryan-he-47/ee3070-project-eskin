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
  if (row>=15||col>=15){return;}
  eskinMatrix* lastFrame=getCachePressPtr(1);
  QueueHandle_t output=_midiQueue;
  MIDIEvent event;
  if(lastFrame==nullptr){return;}
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
      event.data2=max(lastPressure,currentPressure);
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

// 将-1.0到1.0的浮点偏移量映射到MIDI PitchBend的data1和data2
// 返回值：void，通过引用参数返回映射后的data1和data2
void mapFloatToPitchBend(float offset, uint8_t& data1, uint8_t& data2) {
    // 约束输入范围
    if(offset < -1.0f) offset = -1.0f;
    if(offset > 1.0f) offset = 1.0f;
    
    // 将-1到1映射到0到16383（14位pitchbend范围）
    int pitchBendValue = (int)((offset + 1.0f) * 8191.5f);
    
    // 分解为两个7位字节
    data1 = pitchBendValue & 0x7F;        // LSB (低7位)
    data2 = (pitchBendValue >> 7) & 0x7F; // MSB (高7位)
}

void PressToMIDI::_basicMPE(int row,int col,int channel){//MPE
  if((row<=0)||(row>=15)||(col<=0)||(col>=15)){return;}
  eskinMatrix* lastFrame=getCachePressPtr(1);
  QueueHandle_t output=_midiQueue;
  MIDIEvent event;
  if(lastFrame==nullptr){return;}
  const int deadzone=2;
  event.channel=channel;
  event.data1=_usingConfig.pitchMap[row][col];
  event.MPEnote=_usingConfig.pitchMap[row][col];
  int currentPressure=_pressNow[row][col];
  event.data2=currentPressure-_usingConfig.trigThreshMap[row][col]+5;
  if( (currentPressure>=(_usingConfig.trigThreshMap[row][col]+deadzone)) && (_KeyStateMap[row][col]==KeyState::FREE) ){
    event.type=MIDIEventType::NoteOn;
    xQueueSendToBack(output, &event, 0);
    _banKeys(true,row,col);
    _KeyStateMap[row][col]=KeyState::PRESSING;
  }
  if((currentPressure<(_usingConfig.trigThreshMap[row][col]))&&(_KeyStateMap[row][col]==KeyState::PRESSING)){
    event.type=MIDIEventType::NoteOff;
    event.data2=0;
    xQueueSendToBack(output, &event, portMAX_DELAY);
    _banKeys(false,row,col);
    _KeyStateMap[row][col]=KeyState::FREE;
  }
  
  if(_KeyStateMap[row][col]==KeyState::PRESSING){
    float xbias;
    float ybias;
    float meanF;
    _weightBias(xbias,ybias,row,col,meanF);
    event.type=MIDIEventType::ChannelAT;
    event.data1=meanF*9;
    event.data2=event.data1;
    xQueueSendToBack(output, &event, 0);
    
    uint8_t pb1, pb2;
    mapFloatToPitchBend(ybias, pb1, pb2);
    event.type = MIDIEventType::PitchBend;
    event.data1 = pb1;
    event.data2 = pb2;
    xQueueSendToBack(output, &event, 0);
    }
}
void PressToMIDI::_singlePoint(int row,int col,int channel){
  if(row==0&&col==0){
    QueueHandle_t output=_midiQueue;
    MIDIEvent event;
    
    const int deadzone=2;
    float xbias;
    float ybias;
    float meanF;
    int max=0;
    _weightBias(xbias,ybias,row,col,meanF,0,15,0,15);
    event.channel=channel;
    event.data1=60;
    event.data2=max;
    
    _banKeys(true,row,col,0,15,0,15);
    for (int r = 0; r < MATRIX_ROWS; r++) {
      for (int c = 0; c < MATRIX_COLS; c++) {
        if(_pressNow[r][c]>=max){max=_pressNow[r][c];}
      }
    }
    if( (max>=(_usingConfig.trigThreshMap[row][col]+deadzone)) && (_KeyStateMap[row][col]==KeyState::FREE) ){
      event.type=MIDIEventType::NoteOn;
      xQueueSendToBack(output, &event, 0);
      _KeyStateMap[row][col]=KeyState::PRESSING;
    }else if((max<(_usingConfig.trigThreshMap[row][col]))&&(_KeyStateMap[row][col]==KeyState::PRESSING)){
      event.type=MIDIEventType::NoteOff;
      event.data2=0;
      xQueueSendToBack(output, &event, portMAX_DELAY);
      _KeyStateMap[row][col]=KeyState::FREE;
    }else if(_KeyStateMap[row][col]==KeyState::PRESSING){
    
    event.type=MIDIEventType::ChannelAT;
    event.data1=max;
    event.data2=event.data1;
    xQueueSendToBack(output, &event, 0);
    
    uint8_t pb1, pb2;
    mapFloatToPitchBend(ybias, pb1, pb2);
    event.type = MIDIEventType::PitchBend;
    event.data1 = pb1;
    event.data2 = pb2;
    xQueueSendToBack(output, &event, 0);
    }

  }
}

#include <Arduino.h>
#include "src/pressure_process.h"


// process函数
void PressToMIDI::process(eskinMatrix& pressMat) {
  // 更新当前压力矩阵
  _updatePress(pressMat);
  keyAllocator();
  // 业务逻辑写这里
  //debugSend(&_pressNow,"frame done");//向电脑发送调试信息，可选矩阵和字符串


  // 自动缓存当前帧
  addCurrentFrameToCache();
}


//======================按键分配器,在这里添加新按键逻辑的调用===============================================
void PressToMIDI::keyAllocator (){
  for (int row = 0; row < MATRIX_ROWS; row++) {
    for (int col = 0; col < MATRIX_COLS; col++) {
        if(_sensorMap[row][col]!=0){continue;}
        switch (_usingConfig.keyTypeMap[row][col]){
          case KeyType::BASIC_INSTRUMENT :
            _basicInstrument(row,col,_usingConfig.channelMap[row][col]);break;
          case KeyType::PIANO :
            _piano(row,col,_usingConfig.channelMap[row][col]);break;
          case KeyType::BASIC_MPE :
            _basicMPE(row,col,_usingConfig.channelMap[row][col]);break;
          case KeyType::SINGLE_POINT :
          _singlePoint(row,col,_usingConfig.channelMap[row][col]);break;
          case KeyType::VIOLIN :
          _violin(row,col,_usingConfig.channelMap[row][col]);break;
          case KeyType::DRUM :
          _drum(row,col,_usingConfig.channelMap[row][col]);break;
        }
    }
  }
  
}





//==============================按键配置结构体和PressToMIDI类的初始化===============
KeyConfig::KeyConfig(){

  for (int i = 0; i < MATRIX_ROWS; i++) {
    for (int j = 0; j < MATRIX_COLS; j++) {
        keyTypeMap[i][j] = KeyType::BASIC_INSTRUMENT;
        trigThreshMap[i][j]=36;
        pitchMap[i][j]=0;
        channelMap[i][j]=1;

    }
    channelPC[i]=0;
  }
}

KeyConfig defaultCfg;

PressToMIDI::PressToMIDI( QueueHandle_t output,const KeyConfig& cfg) 
  : _usingConfig(cfg), _midiQueue(output) {
  // 初始化缓存为默认值
  for (int i = 0; i < CACHE_SIZE; i++) {
    for (int r = 0; r < MATRIX_ROWS; r++) {
      for (int c = 0; c < MATRIX_COLS; c++) {
        _cachePress[i][r][c] = 0;
        
      }
    }
  }
  // 初始化当前状态
  for (int r = 0; r < MATRIX_ROWS; r++) {
    for (int c = 0; c < MATRIX_COLS; c++) {
      _KeyStateMap[r][c] = KeyState::FREE;
      _sensorMap[r][c]=0;
    }
  }
}
//===================偏移量计算和按键屏蔽==================================

void PressToMIDI::_banKeys(bool ban, int row, int col,int u, int d, int l, int r){
  if(ban){
    for(int i = -u; i <= d; i++){
      for(int j = -l; j <= r; j++){
        _sensorMap[row+i][col+j]++;
      }
    }
    _sensorMap[row][col]--;
  }else{
    for(int i = -u; i <= d; i++){
      for(int j = -l; j <= r; j++){
        _sensorMap[row+i][col+j]--;
      }
    }
    _sensorMap[row][col]++;
  }
}

bool PressToMIDI::_weightBias(float& x, float& y, int row, int col,float& meanF,int u, int d, int l, int r){
  float xnume=0.0; 
  float denom=0.00001;
  float ynume=0.0; 
  if(row-u<0||row+d>15||col-l<0||col+r>15){return false;}
  for(int i = -u; i <= d; i++){
    for(int j = -l; j <= r; j++){

      xnume=xnume+j*(_pressNow[row+i][col+j]-35);
      ynume=ynume+i*(_pressNow[row+i][col+j]-35);
      denom=denom+(_pressNow[row+i][col+j]-35);

    }
  }
  float raw_x = xnume / denom;
  float raw_y = ynume / denom;
  x = 2 * (raw_x + l) / (l + r) - 1.0;
  y = 2 * (raw_y + u) / (u + d) - 1.0;   // 垂直：上→下 映射 0→1
  
  meanF=denom/((u+d+1.0)*(r+l+1.0));
  //Serial.println(meanF);
  return true;
}


//==============================重置cfg==========================

void PressToMIDI::setConfig(const KeyConfig& cfg) {
    _usingConfig = cfg;
    for(int i=0;i<16;i++){
      MIDIEvent evt;  // 结构体名为evt
      evt.type = MIDIEventType::ProgramChange;  // 或你代码中定义的类型常量，比如 0xC0
      evt.channel = i;           // 0–15
      evt.data1 = _usingConfig.channelPC[i];
      evt.data2 = evt.data1;                   // 忽略
      xQueueSend(_midiQueue, &evt, portMAX_DELAY);
    }
}


//============================以下为缓存功能，不用管=========================================

void PressToMIDI::_updatePress(eskinMatrix& pressMat){
    memcpy(_pressNow, pressMat, sizeof(eskinMatrix)); 
}
// 私有拷贝函数
void PressToMIDI::_copyCacheData(eskinMatrix dstPress, const eskinMatrix srcPress) {
    memcpy(dstPress, srcPress, sizeof(eskinMatrix));  
}
int PressToMIDI::_getCacheIndex(int offset) {// 私有辅助：计算缓存索引
  // 边界检查
  if (offset < 0 || offset >= _cacheValidCount) {
    return -1; // 越界返回-1
  }
  // 计算目标索引（反向查找：最新帧是_writeIdx-1）
  int targetIdx = (_cacheWriteIdx - 1 - offset + CACHE_SIZE) % CACHE_SIZE;
  return targetIdx;
}
// 添加当前帧到缓存
void PressToMIDI::addCurrentFrameToCache() {
  
  _copyCacheData(_cachePress[_cacheWriteIdx], _pressNow);
  _cacheWriteIdx = (_cacheWriteIdx + 1) % CACHE_SIZE;
  if (_cacheValidCount < CACHE_SIZE) {
    _cacheValidCount++;
  }
}

// 1. 获取缓存压力矩阵指针
eskinMatrix* PressToMIDI::getCachePressPtr(int offset) {
  int targetIdx = _getCacheIndex(offset);
  if (targetIdx == -1) {
    debugSend(nullptr, "缓存压力矩阵越界：offset=" + String(offset));
    return nullptr; // 越界返回空指针
  }
  // 直接返回缓存数组的指针（无拷贝）
  return &_cachePress[targetIdx];
}

// 2. 获取缓存偏移矩阵指针（三维数组指针）
#include <Arduino.h>
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
        switch (_usingConfig.keyTypeMap[row][col]){
          case KeyType::BASIC_INSTRUMENT :
            _basicInstrument(row,col,_usingConfig.channelMap[row][col]);
        }
    }
  }
  
}





//==============================按键配置结构体和PressToMIDI类的初始化===============
KeyConfig::KeyConfig(){
  for (int i = 0; i < MATRIX_ROWS; i++) {
    for (int j = 0; j < MATRIX_COLS; j++) {
        keyTypeMap[i][j] = KeyType::BASIC_INSTRUMENT;
        trigThreshMap[i][j]=37;
        pitchMap[i][j]=0;
        channelMap[i][j]=1;
    }
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
      
    }
  }
}
//==============================================================







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
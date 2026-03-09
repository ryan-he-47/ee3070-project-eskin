#include <Arduino.h>
#include "pressure_process.h"


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



KeyConfig::KeyConfig(){
  for (int i = 0; i < MATRIX_ROWS; i++) {
            for (int j = 0; j < MATRIX_COLS; j++) {
                keyTypeMap[i][j] = KeyType::BASIC_INSTRUMENT;
                trigThreshMap[i][j]=94;
                pitchMap[i][j]=0;
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
        _cacheBias[i][r][c][0] = 0;
        _cacheBias[i][r][c][1] = 0;
      }
    }
  }
  // 初始化当前状态
  for (int r = 0; r < MATRIX_ROWS; r++) {
    for (int c = 0; c < MATRIX_COLS; c++) {
      _KeyStateMap[r][c] = KeyState::FREE;
      _keyBiasMap[r][c][0] = 0;
      _keyBiasMap[r][c][1] = 0;
    }
  }
}

// process函数
void PressToMIDI::process(eskinMatrix& pressMat) {
  // 更新当前压力矩阵
  _updatePress(pressMat);
  
  // 业务逻辑写这里
  //debugSend(&_pressNow,"frame done");//向电脑发送调试信息，可选矩阵和字符串
  _basicInstrument(_midiQueue);
  // 自动缓存当前帧
  addCurrentFrameToCache();
}

void PressToMIDI::_updatePress(eskinMatrix& pressMat){
  for (int i = 0; i < MATRIX_ROWS; i++) {
    for (int j = 0; j < MATRIX_COLS; j++) {
      _pressNow[i][j] = pressMat[i][j];
    }
  }
}
// 私有拷贝函数
void PressToMIDI::_copyCacheData(eskinMatrix dstPress, 
                                 uint8_t dstBias[][MATRIX_COLS][2], 
                                 const eskinMatrix srcPress, 
                                 const uint8_t srcBias[][MATRIX_COLS][2]) {
  for (int r = 0; r < MATRIX_ROWS; r++) {
    for (int c = 0; c < MATRIX_COLS; c++) {
      dstPress[r][c] = srcPress[r][c];
      dstBias[r][c][0] = srcBias[r][c][0];
      dstBias[r][c][1] = srcBias[r][c][1];
    }
  }
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
  
  _copyCacheData(_cachePress[_cacheWriteIdx], 
                 _cacheBias[_cacheWriteIdx], 
                 _pressNow, 
                 _keyBiasMap);
  _cacheWriteIdx = (_cacheWriteIdx + 1) % CACHE_SIZE;
  if (_cacheValidCount < CACHE_SIZE) {
    _cacheValidCount++;
  }
}
// 获取最新帧
bool PressToMIDI::getLatestCachedFrame() {
  return getCachedFrame(0);
}
// 获取指定帧
bool PressToMIDI::getCachedFrame(int offset) {
  if (offset < 0 || offset >= _cacheValidCount) {
    debugSend(nullptr, "获取缓存帧失败：参数错误/无有效帧");
    return false;
  }
  int targetIdx = (_cacheWriteIdx - 1 - offset + CACHE_SIZE) % CACHE_SIZE;
  _copyCacheData(_pressNow, 
                 _keyBiasMap, 
                 _cachePress[targetIdx], 
                 _cacheBias[targetIdx]);
  return true;
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
uint8_t (*PressToMIDI::getCacheBiasPtr(int offset))[MATRIX_COLS][2] {
  int targetIdx = _getCacheIndex(offset);
  if (targetIdx == -1) {
    debugSend(nullptr, "缓存偏移矩阵越界：offset=" + String(offset));
    return nullptr; // 越界返回空指针
  }
  // 直接返回缓存数组的指针（无拷贝）
  return _cacheBias[targetIdx];
}

void PressToMIDI::_basicInstrument(QueueHandle_t output){
  MIDIEvent event;
  uint8_t threshold;
  static bool flagMap[16][16]={false};
  

  for (int i = 0; i < MATRIX_ROWS; i++) {
    for (int j = 0; j < MATRIX_COLS; j++) {
      if(_usingConfig.keyTypeMap[i][j]==KeyType::BASIC_INSTRUMENT){
        
        threshold=_usingConfig.trigThreshMap[i][j]+10;
        event.channel=1;
        event.data1=i+j+50;
        event.data2=_pressNow[i][j]-80;
        if(_pressNow[i][j]>=threshold&&!flagMap[i][j]){
          event.type=MIDIEventType::NoteOn;
          flagMap[i][j]=1;
          xQueueSendToBack(output, &event, 0);
        }else if(_pressNow[i][j]<threshold&&flagMap[i][j]){
          event.type=MIDIEventType::NoteOff;
          flagMap[i][j]=0;
          xQueueSendToBack(output, &event, 0);
        }

      }

    }
  }
}
  

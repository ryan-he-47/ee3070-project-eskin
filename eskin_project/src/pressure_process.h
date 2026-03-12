#include <cstddef>
#include <stdint.h>
#include "freertos/queue.h"
#ifndef P_PROCESS_H
#define P_PROCESS_H
#include <Arduino.h>
//#include <lib/ESP32_Host_MIDI/src/ESP32_Host_MIDI.h>
#define MATRIX_ROWS 16  // 矩阵行数
#define MATRIX_COLS 16  // 矩阵列数
typedef uint8_t eskinMatrix[MATRIX_ROWS][MATRIX_COLS]; //定义16*16大小的unit8_t数组类，名叫eskinMatrix

void debugSend(eskinMatrix* mat=nullptr, const String& msg="" );//向电脑发送调试信息，可以发送矩阵和字符串


enum class KeyType{
  NO_FUNCTION,
  BASIC_INSTRUMENT,
  PITCH_BEND,
  PIANO
};

struct KeyConfig{//按键配置，每项都是16*16矩阵，储存每个键的配置
  eskinMatrix trigThreshMap;//触发阈值
  KeyType keyTypeMap[MATRIX_ROWS][MATRIX_COLS];//调用触发逻辑的种类标记
  eskinMatrix pitchMap;//每个键的音高
  KeyConfig();//构造函数
};
extern KeyConfig defaultCfg;//默认配置

enum class MIDIEventType : uint8_t {
    NoteOn       = 0x90,
    NoteOff      = 0x80,
    ControlChange = 0xB0,
    ProgramChange = 0xC0,
    PitchBend    = 0xE0,
};


struct MIDIEvent {
    MIDIEventType type = MIDIEventType::NoteOff;
    uint8_t       channel=1;
    uint8_t       data1;
    uint8_t       data2;
};

class PressToMIDI{//将压力信号魔法般地变成midi信号
  public:
  PressToMIDI( QueueHandle_t output = nullptr,const KeyConfig& cfg=defaultCfg);//构造函数，指定配置和输出midi队列的句柄
  eskinMatrix _pressNow;//现在的压力
  enum class KeyState{//定义枚举类来表示键的状态
    FREE,//未被按下
    PRESSING,//正在按下(压力值增大中)
    LIFTING,//正在抬起(压力值减小中)
    HOLD,//在一定压力值内波动
    DOWN_TO_UP,//从按下到抬起的转折
    UP_TO_DOWN,//从抬起到按下的转折
    SENSOR};//用作某一其他键的周围感应器
  KeyState _KeyStateMap[MATRIX_ROWS][MATRIX_COLS];//每个按键的状态
  uint8_t _keyBiasMap[MATRIX_ROWS][MATRIX_COLS][2];//触发点相对于该按键中心的偏移量
  KeyConfig _usingConfig;//传入的配置
  
  void process(eskinMatrix& pressMat);//处理一帧压力矩阵
  //==========缓存的存储/读取整帧缓存方法============================================================
  void addCurrentFrameToCache(); // 将当前_pressNow/_keyBiasMap存入缓存
  bool getLatestCachedFrame();   // 获取最新缓存帧（覆盖当前_pressNow/_keyBiasMap，慎用）
  bool getCachedFrame(int offset);// 获取指定帧（0=最新，1=上一帧，2=最旧，也覆盖，慎用）
  //==========直接访问缓存内的帧的方法（数组越界会返回空指针，使用前请务必判断是否为空！）==============
  eskinMatrix* getCachePressPtr(int offset);// 获取缓存中指定帧的压力矩阵指针（offset=0最新，1上一帧，2最旧）
  uint8_t (*getCacheBiasPtr(int offset))[MATRIX_COLS][2];  // 获取缓存中指定帧的偏移矩阵指针（返回三维数组指针）
  //==========整个缓存功能都是ai写的================================================================
  private:
  static const int CACHE_SIZE = 3; // 缓存深度，固定3帧
  eskinMatrix _cachePress[CACHE_SIZE]; //压力缓存
  uint8_t _cacheBias[CACHE_SIZE][MATRIX_ROWS][MATRIX_COLS][2]; //偏移量缓存
  int _cacheWriteIdx = 0; 
  int _cacheValidCount = 0; 
  QueueHandle_t _midiQueue; // midi队列句柄
  
  // 私有拷贝函数(缓存功能用的)
  void _copyCacheData(eskinMatrix dstPress, 
                      uint8_t dstBias[][MATRIX_COLS][2], 
                      const eskinMatrix srcPress, 
                      const uint8_t srcBias[][MATRIX_COLS][2]);
   // 私有辅助：计算缓存帧的索引（内部复用，也是缓存功能用的）
  int _getCacheIndex(int offset);
  void _updatePress(eskinMatrix& pressMat);
  void _updateBias();


  //=================实现乐器按键逻辑：BasicInstrument===================
  void _basicInstrument(QueueHandle_t output);
  //====================================================================

};



#endif
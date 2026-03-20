
#ifndef P_PROCESS_H
#define P_PROCESS_H
#include <Arduino.h>
#include <cstddef>
#include <stdint.h>
#include "freertos/queue.h"
#include "src/midi_tool.h"
//#include <lib/ESP32_Host_MIDI/src/ESP32_Host_MIDI.h>
#define MATRIX_ROWS 16  // 矩阵行数
#define MATRIX_COLS 16  // 矩阵列数
typedef uint8_t eskinMatrix[MATRIX_ROWS][MATRIX_COLS]; //定义16*16大小的unit8_t数组类，名叫eskinMatrix



//==================按键配置结构体======================
enum class KeyType{
  NO_FUNCTION,
  BASIC_INSTRUMENT,
  PITCH_BEND,
  PIANO,
  GUTAR
};
struct KeyConfig{//按键配置，每项都是16*16矩阵，储存每个键的配置
  eskinMatrix trigThreshMap;//触发阈值
  KeyType keyTypeMap[MATRIX_ROWS][MATRIX_COLS];//调用触发逻辑的种类标记
  eskinMatrix pitchMap;//每个键的音高
  eskinMatrix channelMap;
  KeyConfig();//构造函数
};
extern KeyConfig defaultCfg;//默认配置
//======================================================


//===================MIDI事件结构体=====================
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
    uint8_t       data1=0;
    uint8_t       data2=0;
    uint8_t       MPEnote=128;//有效值为0-127，不是mpe模式的按键设计不要动这个
};

class PressToMIDI{//将压力信号魔法般地变成midi信号
  public:
  PressToMIDI( QueueHandle_t output = nullptr,const KeyConfig& cfg=defaultCfg);//构造函数，指定配置和输出midi队列的句柄
  eskinMatrix _pressNow;//现在的压力
  enum class KeyState{//定义枚举类来表示键的状态
    FREE,//未被按下
    PRESSED,//已经按下
    PRESSING,//正在按下(压力值增大中)
    LIFTING,//正在抬起(压力值减小中)
    HOLD,//在一定压力值内波动
    DOWN_TO_UP,//从按下到抬起的转折
    UP_TO_DOWN,//从抬起到按下的转折
    SENSOR};//用作某一其他键的周围感应器
  KeyState _KeyStateMap[MATRIX_ROWS][MATRIX_COLS];//每个按键的状态
  KeyConfig _usingConfig;//传入的配置
  void process(eskinMatrix& pressMat);//处理一帧压力矩阵
  void keyAllocator();//按键分配器
  //==========不同的乐器按键=========================================================================
  void _basicInstrument(int row,int col,int channel);//这是能响就行基础款，不支持自定义键的音高
  void _piano(int row,int col,int channel);//钢琴，基本上就是基础款，但是按下时候会等到压力由大变小的时候再发声








  //==========整个缓存功能都是ai写的================================================================
  void addCurrentFrameToCache(); // 将当前_pressNow/_keyBiasMap存入缓存
  eskinMatrix* getCachePressPtr(int offset);// 获取缓存中指定帧的压力矩阵指针（offset=0最新，1上一帧，2最旧）                                     
  //==============================================================================================
  
  
  
  protected:
  QueueHandle_t _midiQueue; // midi队列句柄
  private:
  static const int CACHE_SIZE = 12; // 缓存深度，固定3帧
  eskinMatrix _cachePress[CACHE_SIZE]; //压力缓存
  uint8_t _cacheBias[CACHE_SIZE][MATRIX_ROWS][MATRIX_COLS][2]; //偏移量缓存
  int _cacheWriteIdx = 0; 
  int _cacheValidCount = 0; 
  
  // 私有拷贝函数(缓存功能用的)
  void _copyCacheData(eskinMatrix dstPress, const eskinMatrix srcPress);
   // 私有辅助：计算缓存帧的索引（内部复用，也是缓存功能用的）
  int _getCacheIndex(int offset);
  void _updatePress(eskinMatrix& pressMat);


  //====================================================================
};



#endif
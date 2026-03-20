#ifndef MPE_MANAGER_H
#define MPE_MANAGER_H
#include <stdint.h>
#include <Arduino.h>
#include <src/pressure_process.h>
#define MATRIX_ROWS 16  // 矩阵行数
#define MATRIX_COLS 16  // 矩阵列数
typedef uint8_t eskinMatrix[MATRIX_ROWS][MATRIX_COLS]; //定义16*16大小的unit8_t数组类，名叫eskinMatrix




class MPEManager {
  public:
    int16_t noteList[16];
    void setAvaliableChannel(int start, int end=15);
    bool assignChannel(MIDIEvent* event);

  
};



#endif
#ifndef PRESSURE_MATRIX_RECEIVER_H
#define PRESSURE_MATRIX_RECEIVER_H

#include <Arduino.h>
#include <HardwareSerial.h>
#define MATRIX_ROWS 16  // 矩阵行数
#define MATRIX_COLS 16  // 矩阵列数
typedef uint8_t eskinMatrix[MATRIX_ROWS][MATRIX_COLS]; //定义16*16大小的unit8_t数组类，名叫eskinMatrix

// 1. 先定义空Stream类（放在FPGA_Reader.h里，或主程序里）






class PressureMatrixReceiver {
public:
    // 构造函数：指定硬件串口、输出流（默认 Serial）、输出队列(默认为空指针)、传感器映射表（默认使用内置表）
    PressureMatrixReceiver(HardwareSerial& uart, Stream& output = Serial, QueueHandle_t queue=nullptr ,const uint8_t map[16] = nullptr);


    // 初始化 UART
    void begin(unsigned long baudrate, int rx_pin, int tx_pin);

    // 处理接收数据，需在 loop 中频繁调用
    void process();

    // 获取压力矩阵指针（只读），内联实现，减少函数调用
    inline const uint8_t (*getMatrix())[16] {
        return _pressure_grid;
    }

private:
    HardwareSerial& _uart;
    Stream& _output;
    QueueHandle_t _matrixQueue;
    uint8_t _pressure_grid[16][16];
    uint8_t _sensor_map[16];

    enum SyncState { WAIT_HEADER, WAIT_VALUE } _state;
    uint8_t _current_orig_row, _current_col, _current_row;
    int _frame_counter;

    static const uint8_t DEFAULT_MAP[16];
};



class NullStream : public Stream {
public:
    int available() override { return 0; }
    int read() override { return -1; }
    int peek() override { return -1; }
    void flush() override {}
    size_t write(uint8_t) override { return 1; } // 假装写入成功，不做任何操作
};

#endif
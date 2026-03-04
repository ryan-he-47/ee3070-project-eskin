#ifndef PRESSURE_MATRIX_RECEIVER_H
#define PRESSURE_MATRIX_RECEIVER_H

#include <Arduino.h>
#include <HardwareSerial.h>

class PressureMatrixReceiver {
public:
    // 构造函数：指定硬件串口、输出流（默认 Serial）、传感器映射表（默认使用内置表）
    PressureMatrixReceiver(HardwareSerial& uart, Stream& output = Serial, const uint8_t map[16] = nullptr);

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
    uint8_t _pressure_grid[16][16];
    uint8_t _sensor_map[16];

    enum SyncState { WAIT_HEADER, WAIT_VALUE } _state;
    uint8_t _current_orig_row, _current_col, _current_row;
    int _frame_counter;

    static const uint8_t DEFAULT_MAP[16];
};

#endif
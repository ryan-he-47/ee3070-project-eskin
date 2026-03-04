#include "V1.h"
#include <string.h>

// 默认传感器映射表（与原始代码一致）
const uint8_t PressureMatrixReceiver::DEFAULT_MAP[16] = {
    2, 6, 10, 14, 12, 8, 4, 0, 7, 5, 3, 1, 9, 11, 13, 15
};

PressureMatrixReceiver::PressureMatrixReceiver(HardwareSerial& uart, Stream& output, const uint8_t map[16])
    : _uart(uart), _output(output), _state(WAIT_HEADER), _frame_counter(0) {
    memset(_pressure_grid, 0, sizeof(_pressure_grid));
    if (map) {
        memcpy(_sensor_map, map, 16);
    } else {
        memcpy(_sensor_map, DEFAULT_MAP, 16);
    }
}

void PressureMatrixReceiver::begin(unsigned long baudrate, int rx_pin, int tx_pin) {
    _uart.begin(baudrate, SERIAL_8N1, rx_pin, tx_pin);
}

void PressureMatrixReceiver::process() {
    while (_uart.available() > 0) {
        
        uint8_t byte = _uart.read();

        if (_state == WAIT_HEADER) {
            uint8_t orig_row = (byte >> 4) & 0x0F;
            uint8_t col = byte & 0x0F;
            if (orig_row <= 15 && col <= 15) {
                _current_orig_row = orig_row;
                _current_col = col;
                _current_row = _sensor_map[orig_row];
                _state = WAIT_VALUE;
            }
            // 无效 header 直接丢弃
        } else { // WAIT_VALUE
            uint8_t value = byte;
            // 按原始逻辑存储矩阵
            _pressure_grid[15-_current_col][_current_row] = value;
            if (++_frame_counter >= 288) {
                // 完整帧，通过输出流发送二进制矩阵
                _output.write((uint8_t*)_pressure_grid, 256);
                _frame_counter = 0;
            }
            _state = WAIT_HEADER;
        }
    }
}
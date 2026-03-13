#include <Arduino.h>
#include "FPGA_Reader.h"
#include <string.h>
int errorCount=0;
// 默认传感器映射表（与大哥的原始代码一致）
const uint8_t PressureMatrixReceiver::DEFAULT_MAP[16] = {
    2, 6, 10, 14, 12, 8, 4, 0, 7, 5, 3, 1, 9, 11, 13, 15
};

PressureMatrixReceiver::PressureMatrixReceiver(HardwareSerial& uart, Stream& output,QueueHandle_t queue, const uint8_t map[16])
    : _uart(uart), _output(output), _matrixQueue(queue),_state(0), _frame_counter(0) {
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
    
    while (_uart.available() > 32) {
        
        _uart.read(bufferArray,32);
        for(int i=0;i<32;i++){
            uint8_t byte=bufferArray[i];
            if (!_state) {
                uint8_t orig_row = (byte >> 4) & 0x0F;
                uint8_t col = byte & 0x0F;
                _current_col=col;
                _current_row = _sensor_map[orig_row];
                _state = !_state;
            } else { // WAIT_VALUE
                
                uint8_t value = byte;
                if(byte<25){//判断是否为有效值，若无效则说明发生了键值错位，丢弃该值，直接读取下一个值
                    errorCount++;
                    Serial.println("Error: Invalid pressure value received. Total errors: " + String(errorCount));
                }else{
                // 按原始逻辑存储矩阵
                _pressure_grid[15-_current_col][_current_row] = value;
                if (++_frame_counter >= 288) {
                    // 完整帧，通过输出流发送二进制矩阵
                    if(_matrixQueue!=nullptr){
                        xQueueSendToBack(_matrixQueue,_pressure_grid,0);
                    }else{
                        _output.write((uint8_t*)_pressure_grid, 256);
                        
                    }
                    _frame_counter = 0;
                    
                }
                _state = !_state;
                }
            }
        }
    }
}
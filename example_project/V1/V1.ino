#include "V1.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

// 定义队列句柄
QueueHandle_t matrixQueue;

// 自定义Stream，将数据发送到队列
class QueueStream : public Stream {
public:
    size_t write(uint8_t c) override { 
        return 0; // not used
    }
    size_t write(const uint8_t *buffer, size_t size) override {
        if (size == 256) {
            // 尝试发送到队列，不阻塞
            if (xQueueSend(matrixQueue, buffer, 0) != pdPASS) {
                // 队列满，丢弃数据（可添加计数）
            }
            return size;
        }
        return 0;
    }
    int available() override { return 0; }
    int read() override { return -1; }
    int peek() override { return -1; }
    void flush() override {}
};

QueueStream queueStream;
PressureMatrixReceiver receiver(Serial1, queueStream);  // 接收串口 Serial1，输出到queueStream

// 任务函数声明
void taskReceiveFPGA(void *pvParameters);
void task2(void *pvParameters);

void setup() {//初始化
    Serial.begin(115200); // 用于电脑输出
    receiver.begin(115200, 16, 17);  // RX=16, TX=17

    // 创建队列，深度为2，每个元素256字节
    matrixQueue = xQueueCreate(2, 256);
    if (matrixQueue == NULL) {
        Serial.println("Failed to create queue");
        while(1);
    }

    // 创建接收任务，运行在核心0（或核心1，但注意loop也占用核心1）
    xTaskCreatePinnedToCore(
        taskReceiveFPGA,   // 任务函数
        "Receive",     // 任务名
        4096,          // 堆栈大小
        NULL,          // 参数
        1,             // 优先级
        NULL,          // 任务句柄
        0              // 核心0
    );

    // 创建发送任务，运行在核心1
    xTaskCreatePinnedToCore(
        task2,
        "Send",
        4096,
        NULL,
        1,
        NULL,
        1
    );
}

void loop() {// 挂起
    vTaskDelay(portMAX_DELAY);
}

// 接收任务
void taskReceiveFPGA(void *pvParameters) {
    while(1) {

        receiver.process();  // 不断处理串口数据
        // 使用vTaskDelay(1)让出CPU避免占用CPU
        vTaskDelay(1); // 可选
    }
}

// 发送任务
void task2(void *pvParameters) {
    uint8_t trans_mat[256];
    while(1) {
        // 阻塞等待队列中的矩阵数据
        if (xQueueReceive(matrixQueue, trans_mat, portMAX_DELAY) == pdPASS) {
            Serial.write(trans_mat, 256); // 发送到电脑
        }
    }
}
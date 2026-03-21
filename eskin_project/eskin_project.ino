#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

#include <src/FPGA_Reader.h>
#include <src/pressure_process.h>
//#include "src/BLEMidi.h"
#include "src/midi_tool.h"
#include "src/MPE_manager.h"
#include <src/Keyboard.h>

#include <src/config.h>

#define MATRIX_ROWS 16  // 矩阵行数
#define MATRIX_COLS 16  // 矩阵列数

typedef uint8_t eskinMatrix[MATRIX_ROWS][MATRIX_COLS];
//声明压力矩阵队列句柄
QueueHandle_t matrixQueue = xQueueCreate(5, sizeof(eskinMatrix));  // 队列长度，单个矩阵的字节数（16*16=256字节）;  //定义矩阵队列句柄
QueueHandle_t midiQueue = xQueueCreate(15, sizeof(MIDIEvent));
//实例化FPGA接收器
PressureMatrixReceiver receiver(Serial1, Serial, matrixQueue);  // 接收串口 Serial1，输出到matrixQueue, 当queue句柄没有指定时，使用serial打印
//实例化压力处理器
PressToMIDI pressToMIDI(midiQueue);
//实例化MPE通道分配器
MPEManager mpeManager;
//声明任务函数1
void taskReceiveFPGA(void *pvParameters);
void taskProcessMatrix(void *pvParameters);
void taskSendMIDI(void *pvParameters);
void taskCheckKeyboard(void *pvParameters);

void setup() {
  Serial.begin(115200);

  //bleMidiBegin("ESP32-MIDI");
  delay(1000);  //等待串口稳定
  Serial.println("===程序启动===");
  Serial.printf("Free heap:%d\n", ESP.getFreeHeap());
  mpeManager.setAvaliableChannel(2,14);
  receiver.begin(460800, 20, 21);  // RX=16, TX=17
  
  initAllConfigs();

  if (!keyboard.begin()) {// 键盘初始化
      Serial.println(F("Keyboard init failed"));
      while (1);  
  }

  if (matrixQueue == NULL) {  //处理队列创建失败
    Serial.println("Failed to create queue");
    while (1)
      ;
  }
  xTaskCreatePinnedToCore(
    taskReceiveFPGA,                  // 任务函数
    "Receive data stream from fpga",  // 任务名
    2048,                             // 堆栈大小
    NULL,                             // 参数
    1,                                // 优先级
    NULL,                             // 任务句柄
    0                                 // 核心0
  );

  // midi处理任务，运行在核心1
  xTaskCreatePinnedToCore(
    taskProcessMatrix,
    "Process matrix, yield MIDIEvent",
    2048,
    NULL,
    2,
    NULL,
    1);

  xTaskCreatePinnedToCore(
    taskSendMIDI,
    "Receive MIDI event from queue and send",
    1024 * 8,
    NULL,
    2,
    NULL,
    0);

  xTaskCreatePinnedToCore(
        taskCheckKeyboard,
        "Continuously check keyboard",
        1024*8,
        NULL,
        1,
        NULL,
        1
    );
}




void loop() {
  // put your main code here, to run repeatedly:
  vTaskDelay(portMAX_DELAY);
}
void taskReceiveFPGA(void *pvParameters) {
  int maxDelay = 0;
  while (1) {
    //int start = micros();  //调试计时
    receiver.process();    // 不断处理串口数据

    //int end = micros();  //调试计时
                         /*/===========调试实现============/
                Serial.print("latency : ");   //
                int delay=end-start;          //
                Serial.println(delay);        //
                if(delay>maxDelay){           //
                    maxDelay=delay;
                    Serial.print(", max latency:");//
                    Serial.println(maxDelay);            //
                }                             //
                Serial.print(", max latency:");//
                Serial.println(maxDelay);      //
            //================================/*/
    vTaskDelay(1);       // 使用vTaskDelay(1)让出CPU避免占用CPU
  }
}

// 发送任务

void taskProcessMatrix(void *pvParameters) {
  eskinMatrix matrixBuf;
  //int maxDelay=0;
  while (1) {
    // 阻塞等待队列中的矩阵数据
    if (xQueueReceive(matrixQueue, matrixBuf, portMAX_DELAY) == pdPASS) {
      //debugSend(&matrixBuf);
      //int start=micros();//调试计时
      pressToMIDI.process(matrixBuf);
      //int end=micros();//调试计时
      /*/===========调试实现============/
                Serial.print("latency : ");   //
                int delay=end-start;          //
                Serial.println(delay);        //
                if(delay>maxDelay){           //
                    maxDelay=delay;           //
                }                             //
                Serial.print(", max latency:");//
                Serial.println(maxDelay);      //
            //================================/*/
    }
  }
}
void taskSendMIDI(void *pvParameters) {
  MIDIEvent eventBuf;
  uint8_t rawMIDI[3];
  while (1) {
    if (xQueueReceive(midiQueue, &eventBuf, portMAX_DELAY) == pdPASS) {
      
      
      mpeManager.assignChannel(&eventBuf);
      midiEventEncoder(eventBuf, rawMIDI);
      Serial.write(rawMIDI,3);
      int start=micros();
      //bleMidiSendEvent(eventBuf);
      //Serial.println(midiEventToString(eventBuf));
      int end=micros();
    }
  }
}

void taskCheckKeyboard(void *pvParameters){
    while(1){
        keyboard.tickAndProcess();
        vTaskDelay(125);
    }
}
# Project B: ESP32-S3 + ESP32-P4 协作系统

**版本**: v0.1  
**目标**: S3 输入 MIDI → P4 推理续写 → S3 输出合成

---

## 1. 项目结构

```
Project_B_S3_P4_Collab/
├── s3_firmware/
│   ├── eskin_project_p4_enabled/    # 修改版 eskin-project
│   │   ├── eskin_project.ino
│   │   └── src/
│   │       ├── FPGA_Reader.h
│   │       ├── pressure_process.h
│   │       ├── USBMIDI.h
│   │       ├── BLEMidi.h
│   │       ├── midi_router.h        # ← 新增：路由层
│   │       ├── tokenizer.h          # ← 新增：编码器
│   │       └── ...
│   └── libraries/

├── p4_firmware/
│   ├── p4_inference_service/
│   │   ├── main.c                   # 主函数
│   │   ├── CMakeLists.txt
│   │   └── src/
│   │       ├── event_lstm.h         # LSTM 推理
│   │       ├── event_lstm.c
│   │       ├── event_tokenizer.h    # 解码器
│   │       ├── event_tokenizer.c
│   │       ├── uart_protocol.h      # UART 帧协议
│   │       ├── uart_protocol.c
│   │       └── model_weights.h      # 编译进去的权重
│   └── build/

├── shared/
│   ├── uart_protocol.h              # 共享协议定义
│   ├── tokenizer_config.h            # vocab 定义 (两端一致)
│   └── performance_config.h           # 延迟预算配置

└── README.md
```

---

## 2. S3 端修改 (midi_router.h 实现)

```cpp
// s3_firmware/eskin_project_p4_enabled/src/midi_router.h

#ifndef MIDI_ROUTER_H
#define MIDI_ROUTER_H

#include <Arduino.h>
#include <queue>
#include "src/pressure_process.h"
#include "src/tokenizer.h"
#include "src/USBMIDI.h"

enum class RoutingMode {
    DIRECT,           // 仅直接输出（USB/BLE）
    P4_CONTINUATION,  // 仅发送 P4 推理
    HYBRID            // 两者都
};

/**
 * @brief MIDI 路由器 - 管理 S3 和 P4 之间的通信
 * 
 * 职责:
 * 1. 缓冲 MIDI 事件为 Token 序列
 * 2. 根据 CC 控制命令决定是否触发 P4 推理
 * 3. 解析 P4 响应并路由到输出
 */
class MIDIRouter {
private:
    // UART 连接到 P4
    HardwareSerial* uart_p4;
    
    // 编码器 (MIDI 事件 → Token)
    EdgeEventTokenizer tokenizer;
    
    // 上下文缓冲 (最近的 Token)
    std::vector<uint16_t> context_buffer;
    static constexpr size_t MAX_CONTEXT = 512;
    
    // 路由模式
    RoutingMode current_mode = RoutingMode::DIRECT;
    
    // 性能计数
    struct Stats {
        uint32_t total_requests = 0;
        uint32_t total_tokens_sent = 0;
        uint32_t total_tokens_received = 0;
        uint32_t timeout_errors = 0;
    } stats;
    
public:
    /**
     * @brief 构造函数
     * @param uart_pin_rx 接收引脚 (S3 → P4 收)
     * @param uart_pin_tx 发送引脚 (S3 → P4 发)
     */
    MIDIRouter(int uart_pin_rx, int uart_pin_tx) {
        uart_p4 = &Serial2;
        uart_p4->begin(115200, SERIAL_8N1, uart_pin_rx, uart_pin_tx);
        Serial.println("[MIDIRouter] 初始化完成");
    }
    
    /**
     * @brief 处理单个 MIDI 事件，根据模式决定路由
     */
    void route_event(const MIDIEvent& evt) {
        // 编码事件为 Token (可能多个，例如 velocity + note_on)
        std::vector<uint16_t> tokens;
        tokenizer.encode_event(evt, tokens);
        
        // 添加到上下文缓冲
        for (uint16_t t : tokens) {
            context_buffer.push_back(t);
        }
        while (context_buffer.size() > MAX_CONTEXT) {
            context_buffer.erase(context_buffer.begin());
        }
        
        // 路由决策
        switch (current_mode) {
            case RoutingMode::DIRECT:
                // 直接输出，不经过 P4
                usbMidiSendEvent(evt);
                bleMidiSendEvent(evt);
                break;
                
            case RoutingMode::P4_CONTINUATION:
                // 若是 Note On，触发 P4 推理
                if (evt.type == MIDIEventType::NoteOn) {
                    request_p4_continuation();
                }
                // 同时直接输出当前音符
                usbMidiSendEvent(evt);
                break;
                
            case RoutingMode::HYBRID:
                // 两者都做
                usbMidiSendEvent(evt);
                if (evt.type == MIDIEventType::NoteOn) {
                    // 异步请求 P4（不阻塞）
                    xTaskCreate(
                        [](void* arg) {
                            ((MIDIRouter*)arg)->request_p4_continuation();
                            vTaskDelete(NULL);
                        },
                        "P4 Req",
                        1024 * 4,
                        this,
                        1,
                        NULL
                    );
                }
                break;
        }
    }
    
    /**
     * @brief 设置路由模式
     */
    void set_mode(RoutingMode mode) {
        current_mode = mode;
        Serial.printf("[MIDIRouter] 模式切换: %d\n", (int)mode);
    }
    
    /**
     * @brief 根据 CC 控制器改变模式
     * CC #20: 切换到 P4_CONTINUATION
     * CC #21: 切换到 DIRECT
     * CC #22: 切换到 HYBRID
     */
    void handle_cc(uint8_t cc_number, uint8_t cc_value) {
        if (cc_value < 64) return;  // 忽略低于 64 的值
        
        switch (cc_number) {
            case 20: set_mode(RoutingMode::P4_CONTINUATION); break;
            case 21: set_mode(RoutingMode::DIRECT); break;
            case 22: set_mode(RoutingMode::HYBRID); break;
            default: break;
        }
    }
    
private:
    /**
     * @brief 请求 P4 生成续写
     * 
     * 步骤:
     * 1. 提取上下文的最后 256 个 Token
     * 2. 打包成 UART 帧
     * 3. 发送到 P4
     * 4. 等待响应 (500ms 超时)
     * 5. 解码响应 Token → MIDI 事件
     * 6. 输出 MIDI
     */
    void request_p4_continuation(
        size_t prompt_len = 256,
        size_t max_gen =  160
    ) {
        static uint32_t call_count = 0;
        call_count++;
        
        uint32_t start_time = millis();
        
        // 1. 提取上下文
        size_t start_idx = context_buffer.size() > prompt_len
                         ? context_buffer.size() - prompt_len
                         : 0;
        std::vector<uint16_t> prompt(
            context_buffer.begin() + start_idx,
            context_buffer.end()
        );
        
        Serial.printf("\n[P4 Request #%u] Prompt: %d tokens, ", call_count, prompt.size());
        
        // 2. 发送请求帧
        uart_write_frame(uart_p4, (uint8_t*)prompt.data(), prompt.size());
        
        // 3. 等待响应
        uint8_t response_buffer[256];
        int response_len = uart_read_frame(
            uart_p4,
            response_buffer,
            256,
            500  // 500ms 超时
        );
        
        if (response_len <= 0) {
            Serial.println("✗ 超时或错误");
            stats.timeout_errors++;
            return;
        }
        
        // 4. 解码并输出
        int midi_count = 0;
        for (int i = 0; i < response_len; i++) {
            // response_buffer[i] 是 Token ID
            // 解码为时间戳和 MIDI 事件
            
            MIDIEvent evt = tokenizer.decode_token(response_buffer[i]);
            if (evt.type != MIDIEventType::NoteOff) {
                // 有效事件
                usbMidiSendEvent(evt);
                bleMidiSendEvent(evt);
                midi_count++;
            }
        }
        
        uint32_t elapsed = millis() - start_time;
        Serial.printf("%d tokens → %d MIDI, latency: %u ms\n",
                     response_len, midi_count, elapsed);
        
        // 更新统计
        stats.total_requests++;
        stats.total_tokens_sent += prompt.size();
        stats.total_tokens_received += response_len;
    }
    
    // ──────────────────── UART 帧协议 ────────────────────
    
    /**
     * @brief 写 UART 帧
     * 帧格式: [0xAA 0x55] [LEN_H LEN_L] [DATA...] [CRC8] [0xFF]
     */
    void uart_write_frame(HardwareSerial* uart,
                          const uint8_t* data,
                          size_t len) {
        uint8_t header[4] = {0xAA, 0x55, (uint8_t)(len >> 8), (uint8_t)len};
        uart->write(header, 4);
        uart->write(data, len);
        
        uint8_t crc = compute_crc8(data, len);
        uint8_t tail[2] = {crc, 0xFF};
        uart->write(tail, 2);
    }
    
    /**
     * @brief 读 UART 帧，带超时
     */
    int uart_read_frame(HardwareSerial* uart,
                       uint8_t* out_data,
                       size_t max_len,
                       uint32_t timeout_ms) {
        uint32_t deadline = millis() + timeout_ms;
        
        // 查找帧头
        while (millis() < deadline) {
            if (uart->available() >= 2) {
                uint8_t b0 = uart->read();
                if (b0 == 0x55 && uart->available() > 0) {
                    uint8_t b1 = uart->read();
                    if (b1 == 0xAA) {
                        // 找到 [0x55 0xAA]，开始读长度
                        return uart_read_frame_body(uart, out_data, max_len, deadline);
                    }
                }
            }
        }
        return -1;  // 超时
    }
    
    int uart_read_frame_body(HardwareSerial* uart,
                            uint8_t* out_data,
                            size_t max_len,
                            uint32_t deadline) {
        // 读长度字段
        while (millis() < deadline && uart->available() < 2);
        if (millis() >= deadline) return -1;
        
        uint16_t len = ((uint16_t)uart->read() << 8) | uart->read();
        if (len > max_len) return -1;
        
        // 读数据
        while (millis() < deadline && uart->available() < len + 2);
        if (millis() >= deadline) return -1;
        
        uart->readBytes(out_data, len);
        uint8_t crc = uart->read();
        uint8_t tail = uart->read();
        
        if (tail != 0xFF) return -1;
        if (crc != compute_crc8(out_data, len)) return -1;
        
        return (int)len;
    }
    
    uint8_t compute_crc8(const uint8_t* data, size_t len) {
        uint8_t crc = 0;
        for (size_t i = 0; i < len; i++) {
            crc = crc ^ data[i];
            for (int j = 0; j < 8; j++) {
                crc = (crc << 1) ^ (0x107 & (-(crc >> 7)));
            }
        }
        return crc;
    }

public:
    /**
     * @brief 获取性能统计
     */
    void print_stats() {
        Serial.printf("\n[MIDIRouter Stats]\n");
        Serial.printf("  总请求数: %u\n", stats.total_requests);
        Serial.printf("  发送 Token: %u\n", stats.total_tokens_sent);
        Serial.printf("  接收 Token: %u\n", stats.total_tokens_received);
        Serial.printf("  超时错误: %u\n", stats.timeout_errors);
    }
};

#endif // MIDI_ROUTER_H
```

---

## 3. S3 固件集成

```cpp
// s3_firmware/eskin_project_p4_enabled/eskin_project.ino

#include "src/midi_router.h"

MIDIRouter router(
    47,  // RX 引脚 (S3 RX2)
    21   // TX 引脚 (S3 TX2)
);

void taskSendMIDI(void *pvParameters) {
    MIDIEvent eventBuf;
    
    while (1) {
        if (xQueueReceive(midiQueue, &eventBuf, portMAX_DELAY) == pdPASS) {
            
            if (mpeManager.assignChannel(&eventBuf)) {
                
                // CC 控制处理
                if (eventBuf.type == MIDIEventType::ControlChange) {
                    router.handle_cc(eventBuf.data1, eventBuf.data2);
                }
                
                // 路由
                router.route_event(eventBuf);
            }
        }
    }
}

void setup() {
    Serial.begin(460800);
    bleMidiBegin("ESP32-MIDI-S3");
    usbMidiBegin();
    
    // ... 初始化 FPGA, 压力处理等 (保持) ...
    
    Serial.println("[S3] 启动完成，等待 P4 连接");
    
    // 任务创建 (保持原有)
    xTaskCreatePinnedToCore(taskReceiveFPGA, "Receive FPGA", 2048, NULL, 1, NULL, 0);
    xTaskCreatePinnedToCore(taskProcessMatrix, "Process", 2048, NULL, 2, NULL, 1);
    xTaskCreatePinnedToCore(taskSendMIDI, "Send MIDI", 1024*8, NULL, 2, NULL, 0);
}

void loop() {
    // 定期打印统计
    static uint32_t last_log = 0;
    if (millis() - last_log > 10000) {
        router.print_stats();
        last_log = millis();
    }
}
```

---

## 4. P4 固件核心实现

### 4.1 LSTM 推理核心 (event_lstm.h)

```cpp
// p4_firmware/src/event_lstm.h

#ifndef EVENT_LSTM_H
#define EVENT_LSTM_H

#include <cstddef>
#include <cstdint>
#include <cmath>
#include "esp_nn.h"

/**
 * @brief P4 上的 INT8 LSTM 推理引擎
 * 
 * 权重存储:
 * - FLASH 分区存储量化权重 (1.5 MB)
 * - 运行时从 FLASH → PSRAM 缓冲
 * 
 * 隐态精度:
 * - 输入/隐态: INT8 (节省内存)
 * - 偏置: FP32 (提高数值稳定性)
 */
class P4EventLSTM {
public:
    // 常数定义
    static constexpr uint16_t VOCAB_SIZE = 311;
    static constexpr uint16_t HIDDEN_SIZE = 768;
    static constexpr uint16_t NUM_LAYERS = 2;
    static constexpr float QUANTIZATION_SCALE = 127.0f;
    
    // Token ID 定义
    static constexpr uint16_t PAD_TOKEN = 0;
    static constexpr uint16_t BOS_TOKEN = 1;
    static constexpr uint16_t EOS_TOKEN = 2;
    
    struct HiddenState {
        // INT8 隐态 (节省 50% 内存)
        int8_t h[NUM_LAYERS][HIDDEN_SIZE];      // 隐态向量
        int8_t c[NUM_LAYERS][HIDDEN_SIZE];      // Cell 状态
        
        // FP32 的动态范围数据 (用于反量化)
        float h_scale[NUM_LAYERS];               // 隐态缩放因子
        
        void reset() {
            memset(h, 0, sizeof(h));
            memset(c, 0, sizeof(c));
            for (int i = 0; i < NUM_LAYERS; i++) {
                h_scale[i] = 1.0f / QUANTIZATION_SCALE;
            }
        }
    };
    
    /**
     * @brief 单步推理 (一个 Token → logits)
     */
    void inference_step(
        uint16_t input_token,
        HiddenState& state,
        float* out_logits  // [VOCAB_SIZE]
    ) {
        // 1. 嵌入查表
        const int8_t* embedding_vec = get_embedding(input_token);
        
        // 2. LSTM 前向 (2 层)
        int8_t layer_input[HIDDEN_SIZE];
        memcpy(layer_input, embedding_vec, HIDDEN_SIZE);
        
        for (int layer = 0; layer < NUM_LAYERS; layer++) {
            lstm_cell_int8(
                layer_input,
                state.h[layer],
                state.c[layer],
                out_logits  // 中间输出
            );
            // 反量化为 FP32 用于下一层
            // (实际实现中可优化)
        }
        
        // 3. 投影到词表 (INT8 · INT8 → FP32)
        matmul_s8_f32(
            state.h[NUM_LAYERS - 1],  // 最后一层隐态
            HIDDEN_SIZE,
            projection_weights,        // [HIDDEN_SIZE × VOCAB_SIZE]
            VOCAB_SIZE,
            out_logits
        );
    }
    
    /**
     * @brief 批量生成 (用户调用的高层接口)
     */
    void generate(
        const uint16_t* input_tokens,
        size_t input_len,
        uint16_t* output_tokens,
        size_t& output_len,
        size_t max_tokens = 160
    ) {
        HiddenState state;
        state.reset();
        
        // 1. 吸收输入上下文 (更新隐态)
        float temp_logits[VOCAB_SIZE];
        for (size_t i = 0; i < input_len; i++) {
            inference_step(input_tokens[i], state, temp_logits);
        }
        
        // 2. 生成续写
        output_len = 0;
        for (size_t i = 0; i < max_tokens; i++) {
            float logits[VOCAB_SIZE];
            uint16_t last_token = (i == 0)
                                ? input_tokens[input_len - 1]
                                : output_tokens[i - 1];
            
            inference_step(last_token, state, logits);
            
            // 采样
            uint16_t next_token = sample(logits, temp=1.0f, top_k=8, top_p=0.95f);
            output_tokens[i] = next_token;
            output_len++;
            
            if (next_token == EOS_TOKEN) {
                break;  // 生成完毕
            }
        }
    }
    
private:
    // 权重数据 (编译进固件)
    const int8_t* embedding_weights;   // [VOCAB_SIZE × HIDDEN_SIZE]
    const int8_t* projection_weights;  // [HIDDEN_SIZE × VOCAB_SIZE]
    // LSTM 权重 (每层)
    const int8_t* w_ii, *w_if, *w_ig, *w_io;  // Input-to-hidden
    const int8_t* w_hi, *w_hf, *w_hg, *w_ho;  // Hidden-to-hidden
    const float* b_i, *b_f, *b_g, *b_o;       // 偏置 (FP32)
    
    const int8_t* get_embedding(uint16_t token) {
        return embedding_weights + token * HIDDEN_SIZE;
    }
    
    void lstm_cell_int8(
        const int8_t* x,                    // 输入 [HIDDEN_SIZE]
        int8_t* h,                         // 隐态 [HIDDEN_SIZE]
        int8_t* c,                         // Cell 状态
        float* out_h_fp32                  // 输出 (FP32，用于反量化)
    ) {
        // 计算四个门: i, f, g, o
        // 使用 esp_nn_mat_mul_s8_f32 (INT8 · INT8 → FP32)
        
        // i_gate = sigmoid(W_ii @ x + W_hi @ h + b_i)
        float i_pre[HIDDEN_SIZE];
        esp_nn_mat_mul_s8_f32(x, HIDDEN_SIZE, w_ii, HIDDEN_SIZE, i_pre);
        // ... 加 hidden 部分 ...
        // ... 应用 sigmoid ...
        
        // 类似计算 f, g, o ...
        // c_new = f ⊙ c + i ⊙ tanh(g)
        // h_new = o ⊙ tanh(c_new)
        
        // 量化回 INT8
        // ... 实现细节省略 ...
    }
    
    void matmul_s8_f32(
        const int8_t* a,        // [M]
        size_t M,
        const int8_t* b,        // [M × N]
        size_t N,
        float* out              // [N]
    ) {
        // 使用 esp-nn 的优化实现
        esp_nn_mat_mul_s8_f32(a, M, b, N, out);
    }
    
    uint16_t sample(const float* logits, float temp, int top_k, float top_p) {
        // Softmax → 采样
        // (实现见 P4 固件草案的第 5 部分)
        return 0;  // 占位
    }
};

#endif // EVENT_LSTM_H
```

### 4.2 主固件入口 (main.c)

```c
// p4_firmware/main.c

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_timer.h"

#include "src/event_lstm.h"
#include "src/event_tokenizer.h"
#include "uart_protocol.h"

P4EventLSTM model;
P4EventTokenizer tokenizer;

void task_uart_listener(void *pvParameters) {
    uint8_t uart_buffer[512];
    uint16_t input_tokens[512];
    uint16_t output_tokens[200];
    size_t output_len = 0;
    
    while (1) {
        // 等待 UART 请求帧
        int frame_len = uart_read_frame_blocking(UART_NUM_2, uart_buffer, 512, 5000);
        
        if (frame_len > 0) {
            // 解析 Token
            size_t input_len = 0;
            for (int i = 0; i < frame_len; i++) {
                input_tokens[input_len++] = (uint16_t)uart_buffer[i];
            }
            
            // 推理
            uint64_t start_t = esp_timer_get_time();
            model.generate(input_tokens, input_len, output_tokens, output_len, 160);
            uint64_t elapsed_us = esp_timer_get_time() - start_t;
            
            // 发送响应
            uart_write_frame(UART_NUM_2, (uint8_t*)output_tokens, output_len);
            
            // 日志
            printf("[P4] Inferred %d tokens in %u us (%.3f ms/token)\n",
                  (int)output_len, (unsigned)elapsed_us,
                  (float)elapsed_us / output_len / 1000.0f);
        }
        
        vTaskDelay(10);
    }
}

void app_main() {
    printf("[P4] Firmware starting...\n");
    
    // 初始化 UART2
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    uart_param_config(UART_NUM_2, &uart_config);
    uart_set_pin(UART_NUM_2, 17, 18, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    uart_driver_install(UART_NUM_2, 1024, 1024, 0, NULL, 0);
    
    // 加载模型权重
    if (!model.load_weights_from_flash()) {
        printf("[P4] ✗ Model load failed!\n");
        while (1) vTaskDelay(1000);
    }
    printf("[P4] ✓ Model loaded\n");
    
    // 启动推理任务
    xTaskCreatePinnedToCore(
        task_uart_listener,
        "P4 LSTM",
        1024 * 6,  // 栈空间 (包含隐态缓冲)
        NULL,
        2,         // 高优先级
        NULL,
        0          // Core 0
    );
}
```

---

## 5. 编译部署

### S3 编译（Arduino IDE）

```bash
# 1. 复制 libraries/ 到 Arduino 库目录
cp -r libraries/* ~/Arduino/libraries/

# 2. 打开 eskin_project.ino，修改库引用为相对路径

# 3. 选择开发板: ESP32-S3-DevKit
# 选择 USB CDC 作为 Serial0

# 4. 编译并上传
```

### P4 编译（ESP-IDF）

```bash
# 1. 设置环境
export IDF_PATH=$HOME/esp-idf
source $IDF_PATH/export.sh

# 2. 配置项目
cd p4_firmware
idf.py set-target esp32p4
idf.py menuconfig
  # 启用 USB UART-only
  # 设置 UART2 pins

# 3. 编译
idf.py build

# 4. 烧写
idf.py -p /dev/ttyUSB0 flash monitor
```

---

## 6. 集成测试步骤

### 步骤 1: 物理连接

```
ESP32-S3             ESP32-P4
  TX2 (Pin 21)  →  RX2 (Pin 18)
  RX2 (Pin 47)  ←  TX2 (Pin 17)
  GND           ↔  GND
```

### 步骤 2: 启动验证

```bash
# S3 日志应显示
[S3] 启动完成，等待 P4 连接

# P4 日志应显示
[P4] Firmware starting...
[P4] ✓ Model loaded

# S3 弹奏，日志应显示
[P4 Request #1] Prompt: 256 tokens, 160 tokens → 88 MIDI, latency: 87 ms
```

### 步骤 3: 性能调优

- 观察延迟是否 < 150ms
- 若超过 150ms，启用 esp-nn 加速或降低推理长度
- 测试不同的 `generate()` 参数影响

---

## 7. 故障处理

| 症状 | 原因 | 修复 |
|------|------|------|
| P4 无法接收数据 | UART 引脚错误 | 检查 S3 TX2/RX2 与 P4 RX2/TX2 接线 |
| 推理结果异常 | 权重加载失败 | 验证 flash 烧写，检查 CRC |
| 超时错误频繁 | P4 推理过慢 | 降低 `max_tokens`，增加 UART 超时 |
| MIDI 音符丢失 | S3 路由缓冲溢出 | 增加 `context_buffer` 大小 |

---

**下一步**: 量化结果验证、实时音频反馈集成、延迟时间线可视化


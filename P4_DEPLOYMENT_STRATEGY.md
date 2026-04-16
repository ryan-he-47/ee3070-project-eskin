# ESP32-P4 AI 协处理器部署方案（技术细节草案）

**文档版本**: v0.1 (2026-04-11)  
**目标硬件**: ESP32-P4、ESP32-S3  
**项目分层**: S3 输入层 + P4 推理层 + S3 输出层

---

## 1. 项目架构总览

### 1.1 双芯片协作模型

```
┌──────────────────────────────────────────────────────────────┐
│                        电脑 DAW / 合成器                      │
│                                                               │
│  ← USB 实时续写 MIDI 码流  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
│                                                             │ │
└──────────────────────────────────────────────────────────────┘  │
                            ↑ ↓                                  │
                       USB MIDI                                  │
                            ↑ ↓                                  │
        ┌───────────────────────────────────────────────┐        │
        │          Project A:                           │        │
        │  S3 → USB MIDI → PC 推理 → 播放 → 电脑合成器 │        │
        └───────────────────────────────────────────────┘        │
                            ↓ ↓ ↓                                │
        ┌───────────────────────────────────────────────┐        │
        │                  Project B:                   │        │
        │  ┌─────────────────────────────────────────┐ │        │
        │  │      ESP32-S3 (MIDI 控制器)             │ │        │
        │  │  ┌──────────────────────────────────┐   │ │        │
        │  │  │ 输入层:                          │   │ │        │
        │  │  │ - FPGA 矩阵解析                  │   │ │        │
        │  │  │ - 压力 → MIDI 事件转换          │   │ │        │
        │  │  │ - 路由分支: [直接播放] [发送P4] │   │ │        │
        │  │  └────┬───────────────────────┬────┘   │ │        │
        │  │       │ UART/SPI (事件 Token) │        │ │        │
        │  └───────┼───────────────────────┼────────┘ │        │
        │          │                       │          │        │
        │  ┌───────┴───────┐       ┌───────┴────────…┐ │        │
        │  │    输出路由    │       │    P4 协处理器  │ │        │
        │  │  - USB Out    │←UART←→│  ┌────────────┐│ │        │
        │  │  - BLE Out    │       │  │ 编码层:    ││ │        │
        │  │               │       │  │ 字节 →    ││ │        │
        │  │               │       │  │ 事件Token ││ │        │
        │  │               │       │  ├────────────┤│ │        │
        │  │               │       │  │ LSTM 推理  ││ │        │
        │  │               │       │  │ (INT8 量化)││ │        │
        │  │               │       │  ├────────────┤│ │        │
        │  │               │       │  │ 解码层:    ││ │        │
        │  │               │       │  │ Token →   ││ │        │
        │  │               │       │  │ 字节流    ││ │        │
        │  │               │       │  └────────────┘│ │        │
        │  └───────────────┘       └────────────────┘ │        │
        │                                              │        │
        │              DUAL-CORE FreeRTOS              │        │
        │         (Core0: I/O | Core1: 推理)           │        │
        └──────────────────────────────────────────────┘        │
                            ↑                                    │
                     MIDI 合成器输出                             │
                            ↓                                    │
┌──────────────────────────────────────────────────────────────┐
│                  USB MIDI → 电脑 DAW 播放 ────────────────→ ┘
└──────────────────────────────────────────────────────────────┘
```

### 1.2 项目分工

#### **Project A: S3 → USB MIDI → PC 推理**
- **输入**: 从 FPGA 矩阵接收压力数据
- **处理**: 压力 → MIDI 事件（保持现有 eskin-project 逻辑）
- **输出**: USB MIDI 字节流 → 电脑
- **推理地点**: **电脑侧** (python 实时模型)
- **适用场景**: 快速原型、交互设计、实时参数调试

#### **Project B: S3 ↔ P4 → S3 协作**
- **S3 职责**:
  - 输入层：压力矩阵 → MIDI 事件 (保持)
  - **路由分支**:
    - 分支1: 直接路由 → USB/BLE 输出（当前演奏）
    - 分支2: 编码为 Token → UART → P4 （续写请求）
  - **接收**: 来自 P4 的续写 Token 流 (UART)
  - **解码**: Token → MIDI 字节 → 合成器
  
- **P4 职责**:
  - **接收**: UART 接收 MIDI 事件 Token 流
  - **推理**: 事件 LSTM → 生成续写 Token
  - **返回**: 续写 Token → UART 回 S3
  - **独立部署**: 可抽离做单独的推理加速卡

---

## 2. MIDI 字节流编码格式设计

### 2.1 基础 MIDI 状态字节编码

**目标**: 在有限带宽 (UART 115200 bps) 下最大化信息密度

#### **方案 1: 直接 MIDI 3-字节格式**（低开销，不可压缩）

```
[Status Byte] [Data1] [Data2]
  
  0x90 pp vv   (Note On  | pitch=pp, velocity=vv)
  0x80 pp 00   (Note Off | pitch=pp)
  0xB0 cc vv   (CC       | controller=cc, value=vv)
```

**传输效率**: 
- 24 fps x 4 字节平均 = 96 字节/秒 (< 1200 bps, 充足)
- 响应延迟: 3-4ms @ 115200 bps

**优点**: 标准化、易测试、兼容所有 MIDI 工具  
**缺点**: 无法利用时间戳、丢包时难以恢复

---

#### **方案 2: 事件 Token 格式**（推荐，与模型一致）

```
┌─────────────────────────────────────────┐
│ 事件编码 (与 mnist 模型的 vocab 对应)    │
├─────────────────────────────────────────┤
│ ID   | 含义                              │
├─────────────────────────────────────────┤
│ 0    | PAD (填充，模型用)                │
│ 1    | BOS (句开始，协议用)              │
│ 2    | EOS (句结束，推理停止标记)        │
│ 3-34 | VELOCITY (32个速度等级)           │
│      | V=3: 速度 1, V=4: 速度 4 ... V=34: 速度 128 │
│ 35-122 | NOTE_ON (88个琴键)             │
│      | N=35: MIDI pitch 21 (A0) ... N=122: MIDI pitch 108 (C8) │
│ 123-210 | NOTE_OFF (88个琴键)            │
│      | N=123: pitch 21 ... N=210: pitch 108 │
│ 211-310 | TIME_SHIFT (100个时间间隔)    │
│      | T=211: 0ms, T=212: 10ms ... T=310: 990ms │
│ 311-... | 扩展控制CC (可选)              │
└─────────────────────────────────────────┘
```

**传输协议** (UART 协议):
```c
// 字节流结构 (逐个 Token ID 发送)
// 单个发送: [Token_ID] = 2 字节 (大端序，0x00-0x013F)
// 或紧凑格式: [Token_ID_Byte] = 1 字节 (如果 ID < 256)

例: 继续 "A4 (velocity) NOTE_ON NOTE_OFF TIME_SHIFT TIME_SHIFT ..."
    [0x04] [0x41] [0x7B] [0xD3] [0xD4] ...
```

**传输效率**:
- 1 字节/Token (0-255 范围内) 或 2 字节 (256+)
- 推理响应: 160 Token ~ 160 字节 = 13.8ms @ 115200 bps
- **响应延迟 < 50ms** (包含编解码)

**优点**:
- ✅ 与 Python 模型 Token vocab 无缝对接
- ✅ 支持时间戳控制 (TIME_SHIFT Token)
- ✅ 可验证序列完整性 (EOS 分界)
- ✅ 易于扩展 (预留 CC 控制码位)

**缺点**: 需要编码器/解码器在 S3 和 P4 两端

**推荐采用方案 2** (事件 Token 格式)

---

### 2.3 S3 编码器设计 (Token 生成)

```cpp
// eskin_project/src/tokenizer.h
class EdgeEventTokenizer {
public:
    // 参数 (与 Python 一致)
    static constexpr uint16_t VELOCITY_START = 3;
    static constexpr uint16_t NOTE_ON_START  = 35;   // pitch 21-108
    static constexpr uint16_t NOTE_OFF_START = 123;
    static constexpr uint16_t TIME_SHIFT_START = 211;
    static constexpr uint16_t EOS_TOKEN = 2;
    
    // 单个事件编码
    // input: MIDIEvent
    // output: Token ID (16-bit) 或 Token 序列
    uint16_t encode_velocity(uint8_t vel);
    uint16_t encode_note_on(uint8_t pitch);
    uint16_t encode_note_off(uint8_t pitch);
    uint16_t encode_time_shift_ms(uint16_t ms);
    
    // 流式编码 (连续的 MIDI 事件 → Token 序列)
    void encode_midi_event_stream(
        const MIDIEvent* events, 
        size_t count,
        uint16_t* output_tokens,   // 输出 Token 数组
        size_t& output_len           // 输出长度
    );
};

// 使用示例
EdgeEventTokenizer tok;
MIDIEvent evt[4] = {
    {.type=NoteOn, .data1=60, .data2=100},    // C4, velocity 100
    {.type=NoteOn, .data1=64, .data2=100},    // E4
    {.type=NoteOff, .data1=60, .data2=0},
    {.type=NoteOff, .data1=64, .data2=0}
};
uint16_t tokens[10];
size_t n_tokens = 0;
tok.encode_midi_event_stream(evt, 4, tokens, n_tokens);
// 结果: [0x04] [0x3C] [0x40] [0x7B] [0x7F] ... (约6-8 tokens)

// 发送到 UART (P4)
Serial1.write((uint8_t*)tokens, n_tokens);
```

---

### 2.4 P4 解码器设计 (Token → MIDI)

```cpp
// p4_firmware/src/event_tokenizer.h
class P4EventTokenizer {
public:
    static constexpr uint16_t VELOCITY_START = 3;
    static constexpr uint16_t NOTE_ON_START  = 35;
    static constexpr uint16_t NOTE_OFF_START = 123;
    static constexpr uint16_t TIME_SHIFT_START = 211;
    
    // Token 解码
    struct DecodedEvent {
        bool is_valid;
        MIDIEventType type;
        uint8_t pitch;
        uint8_t velocity;
        uint16_t time_shift_ms;
    };
    
    DecodedEvent decode_token(uint16_t token_id);
    
    // 流式解码 (Token 序列 → MIDI 事件流)
    void decode_token_stream(
        const uint16_t* tokens,
        size_t count,
        MIDIEvent* output_events,
        size_t& output_count
    );
};

// 使用示例
P4EventTokenizer decoder;
uint16_t model_output[8] = {0x04, 0x3C, 0x40, 0x7B, 0x7F, ...};
MIDIEvent midi_out[8];
size_t midi_count = 0;
decoder.decode_token_stream(model_output, 8, midi_out, midi_count);

// 结果: midi_out[0-3] 包含 Note On (C4, E4) + Note Off
```

---

## 3. P4 端侧部署方案（核心）

### 3.1 推荐工具链概览

| 工具 | 用途 | 版本 | 用途 |
|------|-------|-------|------|
| **esp-dl** | 深度学习推理框架 | v1.2+ | LSTM 前向推理、INT8 量化 |
| **esp-ppq** | 性能收集 & 分析 | v 最新 | Latency profiling、内存追踪 |
| **esp-nn** | 优化神经网络算子 | v2024.1+ | 加速矩阵乘法 (esp-nnac) |
| **esp32-p4 SDK** | 硬件驱动 | v5.2+ | USB、UART、内存管理 |
| **esp-tflite** | TensorFlow Lite 编译 | v latest | 可选：如果用 TFLite |

### 3.2 模型优化路径 (Python → P4)

#### **阶段 1: 导出与量化（在 PC 侧完成）**

```python
# midi_gen_ai_rewrite/export_for_p4.py
import torch
import numpy as np

# 加载训练好的模型
model = EventLSTMLM.load("runs/event_lm_v1/last.pth")
model.eval()

# ━━━━━━━━━━━━━━━━━━━━━━ 方案 A: torch 量化 ━━━━━━━━━━━━━━━━━━━━━━
# 1. 准备校准数据集 (代表性的 MIDI 片段）
calibration_dataset = load_maestro_sample(n_samples=100, length=512)

# 2. 应用 INT8 量化
model_qat = torch.quantization.quantize_dynamic(
    model,
    qconfig_spec={torch.nn.LSTM: torch.quantization.default_qconfig},
    dtype=torch.qint8
)

# 3. 导出为 ONNX (与 p4 兼容）
torch.onnx.export(
    model_qat,
    torch.randn(1, 512),  # 输入示例 (batch=1, seq_len=512)
    "event_lm_v1_int8.onnx",
    opset_version=14,
    do_constant_folding=True
)

# ━━━━━━━━━━━━━━━━━━━━━━ 方案 B: esp-dl 格式导出 ━━━━━━━━━━━━━━━━━━━━
# esp-dl 支持自定义模型格式
# 导出权重为二进制数组（嵌入式友好）
def export_for_esp_dl(model, output_dir="p4_model"):
    os.makedirs(output_dir, exist_ok=True)
    
    # 提取 LSTM 权重
    lstm = model.lstm
    
    # 权重量化到 INT8
    def quantize_weight(w, scale=127.0):
        w_scaled = (w * scale).clamp(-128, 127).to(torch.int8)
        return w_scaled.numpy()
    
    # 导出各层权重
    for name, param in lstm.named_parameters():
        if 'weight' in name:
            w_int8 = quantize_weight(param)
            np.save(f"{output_dir}/{name}.i8", w_int8)
        elif 'bias' in name:
            # bias 保持 FP32 或 INT32 (取决于 P4 支持)
            np.save(f"{output_dir}/{name}.f32", param.detach().numpy())
    
    # 导出 Embedding 权重
    emb = model.embedding
    emb_w = quantize_weight(emb.weight)
    np.save(f"{output_dir}/embedding.i8", emb_w)
    
    # 导出配置文件
    config = {
        "vocab_size": model.vocab_size,
        "hidden_size": model.hidden_size,
        "num_layers": 2,
        "quantization": "INT8",
        "scale_factor": 127.0
    }
    with open(f"{output_dir}/config.json", "w") as f:
        json.dump(config, f)
    
    print(f"✓ Model exported to {output_dir}")

export_for_esp_dl(model)
```

#### **阶段 2: P4 侧部署**

```cpp
// p4_firmware/src/model_inference.h
#include "esp_dl.h"  // esp-dl 库

class EdgeEventLSTM {
private:
    // 权重存储 (FLASH 或 PSRAM)
    int8_t* w_ih;      // Input-Hidden weights (INT8)
    int8_t* w_hh;      // Hidden-Hidden weights (INT8)
    float* bias;       // Bias (FP32)
    int8_t* embedding; // Embedding (INT8)
    
    // 量化参数
    float scale_factor = 127.0f;
    
    uint16_t vocab_size = 311;
    uint16_t hidden_size = 768;
    
public:
    struct HiddenState {
        int8_t h[768];  // 隐态 (INT8，节省内存)
        int8_t c[768];  // Cell 状态 (INT8)
        // 或在需要时动态转为 FP32: float h_f32[768];
    };
    
    EdgeEventLSTM() {
        // 从 FLASH 加载权重
        load_weights_from_flash();
    }
    
    // 单步推理: 前向传播一个 Token
    uint16_t inference_step(
        uint16_t input_token,
        HiddenState& state  // 输入和更新隐态
    ) {
        // 1. Embedding 查表 (INT8)
        int8_t* emb_vec = embedding + input_token * hidden_size;
        
        // 2. LSTM 单步
        //    h_new = LSTM_cell(emb_vec, h_old, c_old)
        //    使用 esp-nn 的矩阵乘(nnac_mat_mul_s8_s8)
        
        int8_t h_new[768];
        esp_nn_lstm_step_s8(
            emb_vec, hidden_size,
            state.h, state.c,
            w_ih, w_hh, bias,
            h_new, // 输出
            state.c  // 更新 C
        );
        memcpy(state.h, h_new, 768);
        
        // 3. 投影到 vocab (int8 * int8 → float)
        //    score[vocab_idx] = dot(h_new, projection_w)
        float logits[311];
        esp_nn_mat_mul_s8_f32(
            h_new, hidden_size,
            projection_w, 311,
            logits
        );
        
        // 4. Sampling (温度、top-k、top-p)
        uint16_t next_token = sample_from_logits(logits, temp=1.0f);
        
        return next_token;
    }
    
    // 实时推理循环
    void generate_continuation(
        const uint16_t* input_tokens,
        size_t input_len,
        uint16_t* output_tokens,
        size_t max_output_len,
        size_t& output_len
    ) {
        HiddenState state = {};
        
        // 1. 吸收输入上下文 (更新隐态，不产生输出)
        for (size_t i = 0; i < input_len; i++) {
            (void) inference_step(input_tokens[i], state);
        }
        
        // 2. 生成续写
        output_len = 0;
        for (size_t i = 0; i < max_output_len; i++) {
            uint16_t token = inference_step(
                (i == 0) ? input_tokens[input_len - 1] : output_tokens[i - 1],
                state
            );
            output_tokens[i] = token;
            output_len++;
            
            if (token == EOS_TOKEN) break;  // 生成完成标记
        }
    }
};
```

### 3.3 通信协议 (S3 ↔ P4)

#### **UART 帧格式**

```c
// ━━━━━━━━━━━━━━━ S3 → P4 (请求) ━━━━━━━━━━━━━━━━
// 帧头: [0xAA] [0x55]
// 帧长: [LEN_H] [LEN_L]              // 有效数据长度
// 数据: [Token_0] [Token_1] ... [Token_N]
// 校验: [CRC8]
// 帧尾: [0xFF]

// 例子: 发送 4 个 Token (0x04, 0x3C, 0x40, 0x7B)
// [0xAA][0x55] [0x00][0x04] [0x04][0x3C][0x40][0x7B] [CRC] [0xFF]

// ━━━━━━━━━━━━━━━ P4 → S3 (响应) ━━━━━━━━━━━━━━━━
// 帧头: [0x55] [0xAA]
// 帧长: [LEN_H] [LEN_L]              // 生成的 Token 个数
// 数据: [Token_0] [Token_1] ... [Token_M]
// 校验: [CRC8]
// 帧尾: [0xFF]
```

#### **P4 固件主循环**

```cpp
// p4_firmware/main.c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "src/model_inference.h"
#include "src/event_tokenizer.h"

EdgeEventLSTM model;
P4EventTokenizer decoder;

void task_p4_inference(void *pvParameters) {
    uint16_t input_tokens[512];
    size_t input_len = 0;
    uint16_t output_tokens[200];
    size_t output_len = 0;
    
    uint8_t uart_buffer[256];
    int bytes_read;
    
    while (1) {
        // 1. 接收来自 S3 的 Token 序列
        bytes_read = uart_read_frame(UART_NUM_2, uart_buffer, 256);
        
        if (bytes_read > 0) {
            // 2. 解析 Token（从字节到 Token ID）
            input_len = 0;
            for (int i = 0; i < bytes_read; i++) {
                input_tokens[input_len++] = (uint16_t)uart_buffer[i];
            }
            
            // 3. 运行推理 (延迟 < 100ms)
            uint64_t start_time = esp_timer_get_time();
            model.generate_continuation(
                input_tokens, input_len,
                output_tokens, 200, output_len
            );
            uint64_t elapsed_us = esp_timer_get_time() - start_time;
            
            // 4. 发送响应帧 (Token 序列）
            uart_write_frame(UART_NUM_2, (uint8_t*)output_tokens, output_len);
            
            // 性能日志
            Serial.printf("[P4] Inference: %d us / %d tokens (%.2f ms per token)\n",
                         elapsed_us, output_len, (float)elapsed_us / output_len / 1000.0f);
        }
        
        vTaskDelay(10);  // 10ms poll
    }
}

void setup() {
    Serial.begin(460800);
    uart_init(UART_NUM_2, 115200);  // S3 通信
    
    // 加载模型权重到 PSRAM
    if (!model.load_weights_from_flash()) {
        Serial.println("✗ Model load failed!");
        while (1);
    }
    
    Serial.println("✓ P4 LSTM firmware ready");
    
    // 启动推理任务
    xTaskCreatePinnedToCore(
        task_p4_inference,
        "LSTM inference",
        4096 * 2,  // 堆栈 (包含隐态缓冲)
        NULL,
        2,  // 高优先级
        NULL,
        0   // Core 0
    );
}

void loop() {
    // P4 主任务由 FreeRTOS 接管
}
```

---

## 4. S3 侧协调与路由设计

### 4.1 修改 eskin-project 的路由层

```cpp
// eskin_project/src/midi_router.h
#ifndef MIDI_ROUTER_H
#define MIDI_ROUTER_H

#include "Arduino.h"
#include "src/pressure_process.h"
#include "src/tokenizer.h"

enum class MIDIRoute {
    DIRECT_OUTPUT,   // 直接输出 (USB/BLE)
    P4_CONTINUATION, // 发送给 P4 推理
    BOTH             // 两者都
};

class MIDIRouter {
private:
    EdgeEventTokenizer tokenizer;
    HardwareSerial* uart_p4;
    
    // 上下文缓冲 (用于组织 P4 请求)
    std::queue<MIDIEvent> context_buffer;
    static constexpr size_t MAX_CONTEXT = 512;  // Token 个数
    
public:
    MIDIRouter(HardwareSerial* uart_to_p4 = &Serial2) 
        : uart_p4(uart_to_p4) {
        uart_p4->begin(115200, SERIAL_8N1, RX_PIN, TX_PIN);
    }
    
    // 路由单个事件
    void route_midi_event(const MIDIEvent& evt, MIDIRoute mode) {
        if (mode == MIDIRoute::DIRECT_OUTPUT || mode == MIDIRoute::BOTH) {
            usbMidiSendEvent(evt);
            bleMidiSendEvent(evt);
        }
        
        if (mode == MIDIRoute::P4_CONTINUATION || mode == MIDIRoute::BOTH) {
            // 添加到上下文缓冲
            context_buffer.push(evt);
            if (context_buffer.size() > MAX_CONTEXT) {
                context_buffer.pop();  // 滑动窗口
            }
        }
    }
    
    // 触发 P4 推理 (例：当按下特殊按钮时)
    void request_p4_continuation(
        size_t prompt_length = 256,  // 从缓冲末尾取最近的 N Token
        size_t max_generation = 160   // 最多生成多少 Token
    ) {
        // 1. 从缓冲提取最近的 Token
        std::vector<uint16_t> prompt_tokens;
        size_t start_idx = context_buffer.size() > prompt_length
                         ? context_buffer.size() - prompt_length
                         : 0;
        for (size_t i = start_idx; i < context_buffer.size(); i++) {
            // 编码事件为 Token (简化：假设队列可索引)
            uint16_t token = tokenizer.encode_event(context_buffer[i]);
            prompt_tokens.push_back(token);
        }
        
        // 2. 发送请求帧到 P4
        uart_write_frame(uart_p4,
                        (uint8_t*)prompt_tokens.data(),
                        prompt_tokens.size());
        
        // 3. 等待响应 (含超时)
        uint8_t response_buffer[256];
        int response_len = uart_read_frame(uart_p4, response_buffer, 256, 500);  // 500ms timeout
        
        if (response_len > 0) {
            // 4. 解码响应 Token → MIDI 事件
            for (int i = 0; i < response_len; i++) {
                // 这里简化；实际需要处理多字节 Token
                MIDIEvent evt = tokenizer.decode_token(response_buffer[i]);
                route_midi_event(evt, MIDIRoute::DIRECT_OUTPUT);
            }
            Serial.printf("[S3] P4 continuation: %d tokens → MIDI output\n", response_len);
        } else {
            Serial.println("[S3] ✗ P4 timeout or error");
        }
    }
};

#endif
```

### 4.2 集成到 eskin_project.ino

```cpp
// eskin_project/eskin_project.ino (修改)

#include "src/midi_router.h"

MIDIRouter router(&Serial2);  // UART2 → P4

// taskSendMIDI 修改版本
void taskSendMIDI(void *pvParameters) {
    MIDIEvent eventBuf;
    static uint32_t cc_timestamp = 0;  // 用于检测 CC 控制
    
    while (1) {
        if (xQueueReceive(midiQueue, &eventBuf, portMAX_DELAY) == pdPASS) {
            if (mpeManager.assignChannel(&eventBuf)) {
                
                // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                // 路由决策：根据 CC 控制器选择模式
                // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                if (eventBuf.type == MIDIEventType::ControlChange) {
                    // CC #20: 开启 P4 续写模式
                    // CC #21: 直接输出模式
                    // CC #22: 混合模式
                    
                    if (eventBuf.data1 == 20 && eventBuf.data2 > 64) {
                        router.request_p4_continuation(256, 160);
                        cc_timestamp = millis();
                    } else {
                        // 普通 CC 消息直接路由
                        router.route_midi_event(eventBuf, MIDIRoute::DIRECT_OUTPUT);
                    }
                } else {
                    // Note On/Off 根据最后一次 CC 决定路由
                    uint32_t time_since_cc = millis() - cc_timestamp;
                    
                    if (time_since_cc < 500) {  // 500ms 内的 Note 使用 P4
                        router.route_midi_event(eventBuf, MIDIRoute::P4_CONTINUATION);
                    } else {
                        router.route_midi_event(eventBuf, MIDIRoute::DIRECT_OUTPUT);
                    }
                }
                
                usbMidiSendEvent(eventBuf);
                bleMidiSendEvent(eventBuf);
            }
        }
    }
}
```

---

## 5. 延迟预算与性能指标

### 5.1 系统端到端延迟 (S3 → P4 → S3)

```
输入事件 (S3)
    ↓ [0 ms]
编码为 Token (S3 端， esp32-s3 LSTM hidden state 计算)
    ↓ [0.5 ms: tokenizer overhead]
UART 传输 (115200 bps, ~512 Token = ~512 字节)
    ↓ [4.4 ms: 512 字节 / 115200 bps]
接收到 P4
    ↓ [0 ms]
P4 推理 (LSTM 160 Token)
    ↓ [50-100 ms: 160 Token × 0.3-0.6 ms/token]
UART 回复 (160 字节)
    ↓ [1.4 ms]
S3 接收
    ↓ [0.5 ms: 解码 Token → MIDI]
合成器输出
    ↓

┌────────────────────────────────┐
│ 总延迟: 56-107 ms             │
│ (超过 50ms，需要优化)          │
└────────────────────────────────┘
```

**优化策略**:
1. **提前批处理**: 不等单个事件，缓冲 8-16 个事件后统一发送
2. **模型优化**: 用 esp-nn 加速矩阵乘法 (可减少 30-40%)
3. **UART 加速**: 升级到 920600 或 1500000 bps (如硬件支持)
4. **并行推理**: P4 启用双核，一核处理 UART，一核持续推理

### 5.2 内存占用估算

| 模块 | 大小 | 备注 |
|------|------|------|
| LSTM 权重 (INT8) | 768×768×2 layers × 1 byte | ~1.2 MB |
| Embedding (INT8) | vocab 311 × 768 | ~0.24 MB |
| 隐态缓冲 (hidden + cell) | 2×768×2 layers × 4 bytes | ~12 KB |
| UART 缓冲 | 512 Token (2 bytes each) | ~1 KB |
| 模型预测缓冲 | 311 logits × 4 bytes | ~1.3 KB |
| **总计** | | **~1.5 MB** |

**可用空间**: ESP32-P4 内存 ~520 KB SRAM + 16 MB PSRAM，充足。

---

## 6. 工具链快速参考

### 6.1 esp-dl 使用示例

```bash
# 安装
git clone https://github.com/espressif/esp-dl.git
cd esp-dl && python setup.py install

# 导出与量化
python3 -c "
from esp_dl.io import load_pytorch_onnx
from esp_dl.quant import quantize_lstm

# 加载模型
model = load_pytorch_onnx('event_lm_v1.onnx')

# 量化到 INT8
quantized_model = quantize_lstm(model, scale=127.0)

# 导出 C 头文件 (嵌入权重)
quantized_model.export_to_c_header('model.h')
"
```

### 6.2 esp-ppq 性能分析

```bash
# 在 P4 上运行推理，收集性能数据
python3 -c "
from esp_ppq import ProfileTaskScheduler, PerformanceAnalyzer

analyzer = PerformanceAnalyzer('p4_firmware.elf')
analyzer.analyze_latency()
analyzer.print_report()
"
```

### 6.3 esp-nn 优化

```cpp
// 在 inference 中使用 esp-nn 加速矩阵乘法
#include "esp_nn.h"

// 替代标准矩阵乘法
esp_nn_mul_s8(
    input, 512,         // input 矩阵
    weights, 768, 512,  // weight
    output, 768,        // output
    bias,               // bias
    scale_shift
);
```

---

## 7. 在线迭代流程

### 7.1 Project A (S3 → PC): 快速原型

```
eskin_project (S3输入)
    ↓
USB MIDI 字节 → 电脑
    ↓
Python 实时推理 (continuous_generation.py)
    ↓
播放 / 可视化
    ↓
[参数调试] → 重新启动推理
```

**优势**: 快速迭代，无需 P4 固件开发

### 7.2 Project B (S3 ↔ P4): 生产部署

```
eskin_project (修改+midi_router)
    ↓ 
[直接输出 | P4 协作 | 混合]
    ↓
P4 固件 (INT8 推理)
    ↓
UART 回延续的 Token
    ↓
S3 解码输出 → 合成器
```

---

## 8. 检查清单与下一步

- [ ] **PC 侧工具链验证**
  - [ ] 安装 esp-dl
  - [ ] 验证模型导出与量化
  - [ ] 在 PC 上运行 INT8 推理测试

- [ ] **P4 固件框架**
  - [ ] 实现 `EdgeEventLSTM` 推理类
  - [ ] 实现 UART 帧协议
  - [ ] 在 P4 上运行单步推理测试

- [ ] **S3 集成**
  - [ ] 添加 `MIDIRouter` 类
  - [ ] 修改 `taskSendMIDI` 支持条件路由
  - [ ] 集成 CC 控制信号处理

- [ ] **端到端测试**
  - [ ] 单个 MIDI 事件测试 (从 S3 → P4 → S3)
  - [ ] 延迟测试与优化
  - [ ] 实时弹奏测试

---

**下一步**: 需要更详细的吗？建议先完成：
1. ✅ 本草案技术细节定稿
2. ⏳ P4 固件骨架搭建 + esp-dl 集成
3. ⏳ S3 midi_router 模块实现
4. ⏳ 两个 Project 的代码库分离与打包


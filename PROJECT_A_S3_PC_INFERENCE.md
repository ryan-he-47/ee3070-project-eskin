# Project A: ESP32-S3 + PC 实时推理与播放系统

**版本**: v0.1  
**目标**: S3 作为 MIDI 输入设备，电脑上实时推理与播放

---

## 1. 项目结构

```
Project_A_S3_PC_Inference/
├── firmware/
│   ├── s3_midi_input/
│   │   ├── eskin_project/          # 基于现有项目修改
│   │   │   ├── eskin_project.ino
│   │   │   └── src/
│   │   │       ├── FPGA_Reader.h
│   │   │       ├── pressure_process.h
│   │   │       ├── USBMIDI.h       # 改进：只输出 USB MIDI
│   │   │       ├── midi_tool.h
│   │   │       └── ...
│   │   └── libraries/              # 保持现有
│   │
│   └── build/                      # 编译输出

├── pc/
│   ├── real_time_inference.py      # 实时推理脚本
│   ├── midi_synthesizer.py         # 合成与播放
│   ├── requirements.txt
│   └── config.yaml                 # 模型路径、延迟预算配置

└── README.md                        # 快速开始
```

---

## 2. S3 固件简化方案

**变更概述**:
- 保持现有的压力采集、MIDI 事件生成流程
- 输出改为 **仅 USB MIDI 字节流**（不需要路由分支）
- 移除 BLE 广播，简化代码

```cpp
// firmware/s3_midi_input/eskin_project.ino (简化版)

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <src/FPGA_Reader.h>
#include <src/pressure_process.h>
#include "src/USBMIDI.h"

QueueHandle_t matrixQueue = xQueueCreate(5, sizeof(eskinMatrix));
QueueHandle_t midiQueue = xQueueCreate(32, sizeof(MIDIEvent));

void setup() {
    Serial.begin(460800);
    usbMidiBegin();  // 仅启用 USB MIDI
    
    // ... FPGA + 压力处理初始化 (保持不变) ...
    
    xTaskCreatePinnedToCore(taskReceiveFPGA, "Receive FPGA", 2048, NULL, 1, NULL, 0);
    xTaskCreatePinnedToCore(taskProcessMatrix, "Process", 2048, NULL, 2, NULL, 1);
    xTaskCreatePinnedToCore(taskSendMIDI, "Send MIDI", 1024*8, NULL, 2, NULL, 0);
}

void taskSendMIDI(void *pvParameters) {
    MIDIEvent eventBuf;
    while (1) {
        if (xQueueReceive(midiQueue, &eventBuf, portMAX_DELAY) == pdPASS) {
            if (mpeManager.assignChannel(&eventBuf)) {
                // 直接发送 USB MIDI（无路由复杂性）
                usbMidiSendEvent(eventBuf);
            }
        }
    }
}

void loop() {}
```

---

## 3. PC 侧实时推理代码

```python
# pc/real_time_inference.py
import threading
import queue
import mido
import numpy as np
import torch
from midi_gen_ai_rewrite.generate import EventTokenizer, EventLSTMLM, generate_tokens

class PCMIDIInferenceServer:
    def __init__(self, model_path, device="cuda", context_len=512):
        self.model_path = model_path
        self.device = device
        self.context_len = context_len
        
        # 加载模型与 tokenizer
        self.tokenizer = EventTokenizer()
        self.model = EventLSTMLM.load(model_path).to(device).eval()
        
        # 消息队列
        self.input_queue = queue.Queue(maxsize=100)  # MIDI 输入
        self.output_queue = queue.Queue(maxsize=100)  # MIDI 输出
        
        # 上下文缓冲
        self.context_tokens = []
        self.context_lock = threading.Lock()
        
    def input_listener(self):
        """监听 S3 的 USB MIDI 输入"""
        inport = None
        try:
            # 自动查找 S3 MIDI 端口
            for port_name in mido.get_input_names():
                if "ESP32" in port_name or "MIDI" in port_name:
                    inport = mido.open_input(port_name)
                    print(f"✓ 连接到 {port_name}")
                    break
            
            if not inport:
                raise RuntimeError("未找到 S3 MIDI 输入")
            
            for msg in inport:
                # 将 MIDI 消息放入队列
                self.input_queue.put(msg)
                
                # 编码为 Token（用于上下文）
                token = self.tokenizer.encode_midi_msg(msg)
                with self.context_lock:
                    self.context_tokens.append(token)
                    if len(self.context_tokens) > self.context_len:
                        self.context_tokens.pop(0)  # 滑动窗口
                        
        except Exception as e:
            print(f"✗ MIDI 输入错误: {e}")
        finally:
            if inport:
                inport.close()
    
    def inference_worker(self, batch_interval_ms=100):
        """推理工作线程"""
        synth_output = mido.open_output("Microsoft GS Wavetable Synth")  # Windows 输出
        
        while True:
            try:
                # 批处理：等待 batch_interval_ms 或队列满
                batch = []
                deadline = time.time() + batch_interval_ms / 1000.0
                
                while time.time() < deadline:
                    try:
                        msg = self.input_queue.get(timeout=0.01)
                        batch.append(msg)
                    except queue.Empty:
                        break
                
                if batch:
                    # 生成续写
                    with self.context_lock:
                        context = self.context_tokens[-self.context_len:]
                    
                    # 张量化
                    context_tensor = torch.tensor(context, device=self.device).unsqueeze(0)
                    
                    # 推理
                    with torch.no_grad():
                        output_tokens = generate_tokens(
                            self.model,
                            self.tokenizer,
                            context_tensor,
                            max_new_tokens=160,
                            temperature=1.0,
                            top_k=8,
                            top_p=0.95
                        )
                    
                    # 解码为 MIDI 消息
                    for token in output_tokens:
                        msg = self.tokenizer.decode_token_to_midi(token.item())
                        if msg:
                            synth_output.send(msg)
                            self.output_queue.put(msg)
                    
                    print(f"[推理] {len(batch)} 事件 → {len(output_tokens)} 续写 Token")
                    
            except Exception as e:
                print(f"✗ 推理错误: {e}")
    
    def start(self):
        """启动线程"""
        t1 = threading.Thread(target=self.input_listener, daemon=True)
        t2 = threading.Thread(target=self.inference_worker, daemon=True)
        
        t1.start()
        t2.start()
        
        print("✓ 实时推理服务启动")
        
        # 保持运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n关闭...")


if __name__ == "__main__":
    import time
    import yaml
    
    # 加载配置
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    server = PCMIDIInferenceServer(
        model_path=config["model_path"],
        device=config.get("device", "cuda"),
        context_len=config.get("context_len", 512)
    )
    
    server.start()
```

```yaml
# pc/config.yaml
model_path: "path/to/event_lm_v1/last.pth"
device: "cuda"  # 或 "cpu"
context_len: 512
batch_interval_ms: 100
```

---

## 4. 快速开始

### 步骤 1: S3 固件编译与上传

```bash
# 使用 Arduino IDE 或 PlatformIO
cd firmware/s3_midi_input/eskin_project
pio upload --device /dev/ttyUSB0
```

### 步骤 2: PC 环境配置

```bash
cd pc/
pip install -r requirements.txt

# 验证 MIDI 连接
python -c "import mido; print(mido.get_input_names())"
```

### 步骤 3: 启动推理服务

```bash
python real_time_inference.py
```

**预期输出**:
```
✓ 连接到 ESP32-MIDI
✓ 输出到 Microsoft GS Wavetable Synth
✓ 实时推理服务启动
[推理] 4 事件 → 156 续写 Token
...
```

### 步骤 4: 弹奏与测试

- 通过 S3 FPGA 矩阵或键盘输入 MIDI 信号
- 观察电脑端实时生成续写
- 调整推理参数 (temperature, top_k) 影响风格

---

## 5. 性能指标

| 指标 | 目标 | 备注 |
|------|------|------|
| USB MIDI 延迟 | < 5ms | S3 → PC |
| 推理延迟 | 50-150ms | 模型 + 批处理 |
| 吞吐量 | 100-200 事件/秒 | MIDI 输入饱和点 |
| GPU 占用 | ~2GB VRAM | (RTX 3060 水平) |

---

## 6. 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| S3 不识别 | USB 驱动缺失 | 安装 CH340 驱动 |
| 无 MIDI 输入 | 端口查找失败 | 手动指定 `inport = mido.open_input("xxx")` |
| 推理滞后 | GPU 内存不足 | 降低 `batch_interval_ms` 或用 CPU |
| 续写重复 | 模型欠拟合 | 尝试 `temperature=0.8, top_k=5` |

---

**下一步**: 集成音频可视化、MIDI 录制回放等高级功能


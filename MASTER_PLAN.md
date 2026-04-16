# 两层架构完整规划指南

**日期**: 2026-04-11  
**目标**: 建立 MIDI AI 续写系统的两个部署路径

---

## 概览：项目分层结构

```
┌─────────────────────────────────────────────────────────────────┐
│                    MIDI AI 续写系统                             │
│                                                                 │
│  ┌──────────────────────────────┬──────────────────────────┐   │
│  │    Project A: 轻量级方案       │   Project B: 生产部署   │   │
│  │  (原型、设计、参数微调)        │    (嵌入式协处理)      │   │
│  └──────────────────────────────┴──────────────────────────┘   │
│                      │                     │                     │
│  硬件:  S3 + PC      │         硬件:  S3 + P4                   │
│         USB MIDI     │                UART 5V                   │
│         推理地点: PC │          推理地点: P4                    │
│         延迟: 50-150ms│         延迟: 50-100ms                  │
│         优势: 快迭代, 灵活改参  │  优势: 独立部署, 可产品化     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 文档总航图

### 📄 核心文档（按优先级）

| 文件 | 内容 | 用途 | 阅读时长 |
|------|------|------|---------|
| **本文件** | 整体规划与决策指南 | 选择走哪条路 | 5 min |
| **P4_DEPLOYMENT_STRATEGY.md** | 端侧部署技术细节 | P4 架构与编解码方案 | 30 min |
| **PROJECT_A_S3_PC_INFERENCE.md** | 快速原型方案 | 搭建轻量级演示系统 | 20 min |
| **PROJECT_B_S3_P4_COLLAB.md** | 完整协处理方案 | 生产部署架构 | 40 min |
| **TOOLKIT_RESEARCH.md** | 工具链调研 | esp-dl/esp-nn 选型 | 25 min |

---

## 快速决策：我应该做哪个？

### 🎯 选择 Project A，如果你...

✓ 想**快速验证**生成效果  
✓ 需要**灵活调参** (temperature, top_k)  
✓ 已有高性能 PC/GPU  
✓ 不关心**最终的硬件形态**  
✓ 重点是**交互体验**和**参数调优**  

**时间投入**: 3-5 天  
**代码量**: ~500 行 Python  
**工具依赖**: PyTorch, mido, 标准 MIDI 库

---

### 🚀 选择 Project B，如果你...

✓ 想**独立部署**（无 PC 依赖）  
✓ 关注**端到端延迟**和**功耗**  
✓ 需要**可产品化**的解决方案  
✓ 愿意投入**嵌入式开发**  
✓ 有 **ESP32-P4 硬件** 

**时间投入**: 3-4 周  
**代码量**: ~2000 行 (S3 改进 + P4 推理)  
**工具依赖**: ESP-IDF, esp-dl, esp-nn, 量化工具链

---

### 🔀 混合方案 (推荐)

**分阶段推进**:

```
Week 1:  Project A 快速验证 (原型意义)
        └─ 确认模型在实时输入下的表现
        └─ 收集参数调优数据

Week 2-3: Project B 开发 (生产部署)
        └─ P4 推理引擎搭建  
        └─ S3 路由层集成
        └─ 性能优化与测试

Week 4:  两个方案共存
        └─ A 用于算法研发
        └─ B 用于最终交付
```

---

## 分项路线图

### Phase 1: 基础准备 (全项目通用)

- [x] 审视 eskin-project MIDI 架构
- [x] 梳理 Python 模型导出流程
- [ ] **TODO**: 搭建 PC 侧量化 pipeline

```bash
# 任务清单
cd midi_gen_ai_rewrite/
python3 export_for_quantization.py \
    --model runs/event_lm_v1/last.pth \
    --output_dir p4_model/
```

---

### Phase 2a: Project A (轻量级, ~1 周)

**里程碑**:
1. ✓ S3 固件简化版 (仅 USB MIDI)
2. ✓ PC 推理脚本 (`real_time_inference.py`)
3. ✓ 端到端验证

**检查清单**:
- [ ] S3 成功连接 PC (USB MIDI 可见)
- [ ] MIDI 输入 → 电脑 tokenization 正常
- [ ] 推理延迟 < 200ms (可接受)
- [ ] 生成结果音乐学意义 (听测)

**成果**:
- 可交互的实时续写演示
- 参数优化数据 (温度、top-k 敏感性)
- 为 Project B 提供性能基准

---

### Phase 2b: Project B (生产级, ~3-4 周)

#### Phase 2b.1: P4 推理引擎 (~1 周)

**任务**:
1. [ ] 安装 esp-dl, esp-nn
2. [ ] 模型 INT8 量化 (PC 侧)
3. [ ] 导出 C 头文件 (model_weights.h)
4. [ ] P4 固件框架搭建

**验证步骤**:
```bash
# 1. 量化
cd midi_gen_ai_rewrite/
python3 -c "
from esp_dl.quant import quantize_lstm
model = load_pytorch_model('runs/event_lm_v1/last.pth')
quantize_lstm(model).export_to_c_header('p4_weights.h')
"

# 2. P4 编译
cd p4_firmware/
idf.py set-target esp32p4
idf.py build

# 3. 单独测试推理
# (在 p4_firmware/test/test_lstm_inference.c 中)
TEST: single step forward pass
TEST: 160 token generation latency < 100ms
```

#### Phase 2b.2: S3 路由层 (~1 周)

**任务**:
1. [ ] 实现 `midi_router.h` (缓冲 + 编码)
2. [ ] UART 协议实现 (5V 兼容)
3. [ ] 集成到 eskin_project

**验证**:
```
S3 → [UART] → P4: Token 流正确传输
P4 → [UART] → S3: 响应 Token 解码无误
```

#### Phase 2b.3: 集成与优化 (~1-2 周)

**任务**:
1. [ ] 端到端延迟测试
2. [ ] esp-ppq 性能分析
3. [ ] 瓶颈优化 (INT8 SIMD, PSRAM)
4. [ ] 稳定性测试 (8+ 小时连续运行)

**目标指标**:
- [ ] 延迟 < 150ms (P4 推理 < 100ms)
- [ ] 崩溃率 < 5% (生成不崩溃进长沉默)
- [ ] 内存稳定 (无泄漏)

---

## 技术依赖清单

### Phase A (Project A)

```
Python 环境:
├─ torch >= 1.12
├─ mido >= 1.2.10
├─ numpy
├─ pyyaml
└─ scipy (可选: 音频分析)

硬件:
├─ ESP32-S3 (已有 eskin-project)
├─ PC with GPU >= 4GB VRAM (or CPU)
└─ USB MIDI 线缆 (或蓝牙)

依赖库编译:
└─ 无专门编译，纯 Python+PyTorch
```

**安装命令**:
```bash
cd pc/
pip install -r requirements.txt
# requirements.txt:
# torch>=1.12.0
# mido>=1.2.10
# numpy>=1.21
# pyyaml>=5.4
```

---

### Phase B (Project B)

```
PC 侧:
├─ Python >= 3.9
├─ ESP-IDF >= 5.2
├─ esp-dl (from GitHub)
├─ esp-nn (from GitHub)
└─ esp-ppq (in ESP-IDF)

嵌入式:
├─ ESP32-S3 (带 UART2)
├─ ESP32-P4 (EVB 或自设计板)
├─ USB-UART 适配器 (2 个)
└─ 5V 升压模块 (P4 逻辑电平)

编译工具链:
├─ esp-idf/tools/cmake/3.24
├─ xtensa-esp32p4-elf-gcc (10.2)
└─ esptool.py

可选加速:
├─ OpenOCD (JTAG 调试)
└─ esp-idf-extension (VS Code)
```

**快速安装**:
```bash
# ESP-IDF (v5.2)
git clone --branch release/v5.2 https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh

# esp-dl
git clone https://github.com/espressif/esp-dl.git
pip install ./esp-dl

# esp-nn (included in IDF, but fetch latest)
git clone https://github.com/espressif/esp-nn.git components/esp-nn
```

---

## 成本估算

### 硬件成本

| 项目 | 成本 | 备注 |
|------|------|------|
| ESP32-S3-DevKit | $10-15 | 已有 |
| ESP32-P4-EVB | $20-30 | 新购 |
| 串口转 USB (×2) | $5-10 | 调试用 |
| 杜邦线 + 面包板 | $5-10 | 接线 |
| **总计** | **$40-65** | 最小化 |

---

### 时间成本

| 阶段 | Project A | Project B | 累计 |
|------|-----------|-----------|------|
| 基础准备 | 1d | 1d | 1d |
| 开发与集成 | 3-4d | 14-21d | 15-25d |
| 测试与优化 | 1d | 5-7d | 6-8d |
| **总计** | **4-5d** | **20-29d** | **24-34d** |

**建议**: 混合推进 (A + B 并行) 可压缩至 3-4 周

---

## 决策树

```
我要启动 MIDI AI 续写项目吗?
│
├─→ 我只想**快速验证**想法?
│   └─→ Choose PROJECT A
│       Cost: 4-5 days, ~500 lines Python
│       Benefit: 快速迭代, 参数调优灵活
│
├─→ 我要**最终产品化**部署?
│   └─→ Choose PROJECT B
│       Cost: 3-4 weeks, ~2000 lines C++
│       Benefit: 独立形态, 可量产
│
└─→ 我想**最大化学习**和提高?
    └─→ Choose BOTH (混合方案)
        Cost: 3-4 weeks total (并行)
        Benefit: 先原型后优化, 最佳实践
```

---

## 关键里程碑与验收标准

### Milestone 1: 模型可用性验证 (Week 1)

**Project A**:
```
✓ S3 USB MIDI 输入识别
✓ Python 脚本正常运行，不崩溃
✓ 推理延迟 < 200ms
✓ 输出音乐有意义 (不是纯噪声)
```

**Success Criteria**: 可弹奏演示，交互体验良好

---

### Milestone 2: P4 推理引擎可用 (Week 2-3)

**Project B**:
```
✓ P4 固件编译通过
✓ INT8 量化模型加载成功
✓ 单步推理验证 (forward pass 数值正确)
✓ 160 token 生成延迟 < 100ms
```

**Success Criteria**: P4 可独立推理，不依赖 PC

---

### Milestone 3: 端到端集成完成 (Week 3-4)

**Project B**:
```
✓ S3 ↔ P4 UART 通信稳定
✓ 完整流程: 输入 → Token编码 → P4推理 → Token解码 → MIDI输出
✓ 延迟 < 150ms (含 UART 往返)
✓ 连续运行 8+ 小时无崩溃
```

**Success Criteria**: 可部署，定制研究展品或教学工具

---

## 常见陷阱与解决方案

### 陷阱 1: UART 通信不稳定

**症状**: 时常丢包、超时  
**原因**: 波特率设置不当、电平转换问题  
**解决**:
- 降低波特率到 115200 (从 460800)
- 使用 5V 容限 UART 芯片 (如 CP2102)
- 加短 UART 电缆 (< 30 cm)

---

### 陷阱 2: 量化后生成质量下降

**症状**: Token 高度重复、长沉默、奇怪的音符跳跃  
**原因**: INT8 精度不足，特别是在边界值  
**解决**:
- 先用 FP32 验证基准性能
- 用 esp-dl 的 calibration dataset 来量化
- 考虑混合精度 (关键权重用 FP32)
- 或使用 QAT (量化感知训练)

---

### 陷阱 3: P4 推理延迟超预期

**症状**: 160 token 生成 > 150ms  
**原因**: 未启用 esp-nn SIMD，或内存访问低效  
**解决**:
- 启用 `CONFIG_ESP_NN_OPTIMIZATION`
- 使用 esp-ppq 定位瓶颈
- 减少生成长度 (160 → 100)
- 或增加 UART 波特率

---

### 陷阱 4: 内存溢出 (ESP32-S3)

**症状**: 程序 reboot，heap corruption  
**原因**: context buffer 过大，或内存碎片化  
**解决**:
- 限制 context buffer 大小 (< 512 tokens)
- 定期清理队列缓冲
- 使用 PSRAM (如果 S3 有扩展 64 MB)

---

## 技术支持与资源

### 官方文档

- ESP-IDF: https://docs.espressif.com/
- esp-dl: https://github.com/espressif/esp-dl (含示例)
- esp-nn: https://github.com/espressif/esp-nn (性能指南)
- PyTorch Quantization: https://pytorch.org/docs/stable/quantization.html

### 社区论坛

- ESP32 官方论坛: https://esp32.com/
- GitHub Issues: esp-idf, esp-dl, esp-nn
- Stack Overflow: [esp32] tags

### 调试工具

- **VSCode Extension**: Espressif IDF Tools
- **Serial Monitor**: Arduino IDE 或 miniterm.py
- **Performance**: esp-ppq (内置 ESP-IDF)

---

## 后续扩展方向

### 短期 (1-2 月)

- [ ] 添加 MIDI CC 参数实时控制
- [ ] Web UI 可视化生成过程
- [ ] 多模型支持 (快速切换)
- [ ] 音频反馈集成 (延迟感知)

### 中期 (3-6 月)

- [ ] 模型微调流程 (P4 上在线学习?)
- [ ] 多语言/多风格模型训练
- [ ] 硬件优化 (定制 PCB, 功耗测试)
- [ ] 批量量产 (固件打包、烧写脚本)

### 长期 (6-12 月)

- [ ] 移植到其他 MCU (STM32H7, NXP i.MX)
- [ ] 集成更大模型 (Transformer)
- [ ] 云边协同 (P4 + 云端推理后备)
- [ ] 学术论文发布

---

## 最终建议

### ✅ 如果时间充足 (4+ 周)

**推荐**: 混合方案 (A + B 并行)

```
Week 1: Project A 快速原型
        ↓
Week 2-3: Project B 同步开发
        ↓
Week 4: 集成、优化、文档
```

**收益**: 既有快速迭代窗口，又能最终产品化

---

### ✅ 如果时间紧张 (1-2 周)

**推荐**: 只做 Project A

```
Week 1: 完整的 PC 方案演示
        ↓
后续: Project B 作为长期计划
```

**优势**: 快速验证、展示原型、获得反馈

---

### ✅ 如果已投入  (已开始 Project B)

**建议**: 继续深入，不要中途放弃

```
Week 2-3: 完成推理引擎
Week 3-4: 集成与优化
Week 4+: 性能调优与稳定性测试
```

**里程碑**: 给出一个**真正可用的嵌入式系统**

---

**下一步**: 选择你的路径，并按照对应的文档 (PROJECT_A / PROJECT_B / P4_DEPLOYMENT_STRATEGY) 展开！


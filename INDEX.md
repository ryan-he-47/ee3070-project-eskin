# 📚 两层 MIDI AI 续写系统 - 完整文档索引

**文档生成日期**: 2026-04-11  
**项目状态**: ✅ 规划完成，可开始开发

---

## 🎯 快速开始 (5 分钟)

### 我应该做什么？

| 场景 | 推荐方案 | 文档 | 时间 |
|------|--------|------|------|
| 快速验证模型效果 | **Project A** | [PROJECT_A_S3_PC_INFERENCE.md](PROJECT_A_S3_PC_INFERENCE.md) | 4-5 天 |
| 生产化独立部署 | **Project B** | [PROJECT_B_S3_P4_COLLAB.md](PROJECT_B_S3_P4_COLLAB.md) | 3-4 周 |
| 不确定怎么选 | **MASTER_PLAN.md** | [MASTER_PLAN.md](MASTER_PLAN.md) | 5 min |

---

## 📖 完整文档清单

### 核心规划文档

#### 1. **MASTER_PLAN.md** (总策略指南)
- **长度**: 20 分钟阅读
- **内容**:
  - 项目分层结构概览
  - 快速决策树（选 A 还是 B）
  - 混合方案推进时间表
  - 技术依赖清单
  - 常见陷阱与解决方案
  - 成本估算、里程碑定义

**推荐阅读**: 第一个读这个，决定你的路径

---

### Project A: 轻量级方案 (S3 + PC)

#### 2. **PROJECT_A_S3_PC_INFERENCE.md** (快速原型)
- **长度**: 20 分钟阅读
- **系统包含**:
  - S3 固件简化版 (USB MIDI only)
  - PC 实时推理脚本 (`real_time_inference.py`)
  - MIDI 同步合成器集成
  - 故障排查表

**快速开始**:
```bash
# S3: 编译上传 (Arduino IDE)
cd firmware/s3_midi_input/eskin_project
# 上传固件即可

# PC: 安装依赖
pip install -r pc/requirements.txt

# 启动推理
python pc/real_time_inference.py
```

**适用人群**: 想快速验证、需要灵活参数调优、已有 GPU

---

### Project B: 生产部署方案 (S3 + P4)

#### 3. **PROJECT_B_S3_P4_COLLAB.md** (完整协处理系统)
- **长度**: 40 分钟阅读
- **系统包含**:
  - S3 路由层详细实现 (`midi_router.h`)
  - P4 推理引擎代码框架 (`event_lstm.h`)
  - UART 通信协议
  - 编译与部署步骤
  - 集成测试流程

**关键代码**:
- MIDIRouter (S3 端，路由与缓冲)
- P4EventLSTM (P4 端，INT8 推理)
- UART 帧协议实现

**适用人群**: 需要独立部署、关注延迟和功耗、有嵌入式开发经验

---

### 技术深度文档

#### 4. **P4_DEPLOYMENT_STRATEGY.md** (技术细节草案)
- **长度**: 30 分钟阅读
- **核心内容**:
  - 双芯片架构详解
  - MIDI 字节流编码格式设计 (两种方案)
  - P4 端侧部署方案（模型导出、量化、推理）
  - S3 协调与路由设计
  - 延迟预算分析 (56-107 ms)
  - 内存占用估算 (~1.5 MB)
  - 在线迭代流程

**适合角色**: 系统设计师、嵌入式工程师

---

#### 5. **TOOLKIT_RESEARCH.md** (工具链调研)
- **长度**: 25 分钟阅读
- **覆盖主题**:
  - esp-dl (推理框架) 对标
  - esp-nn (神经网络加速) 说明
  - esp-ppq (性能分析) 用法
  - INT8 量化细节与精度验证
  - PyTorch → P4 完整工作流
  - 工具链快速参考表

**适合角色**: 模型优化工程师、工具链选型者

---

## 🗂️ 文档体系关系图

```
MASTER_PLAN.md (总指挥)
    │
    ├─→ 选择 Project A?
    │   └─→ PROJECT_A_S3_PC_INFERENCE.md
    │       └─→ 参考: P4_DEPLOYMENT_STRATEGY (可选)
    │
    └─→ 选择 Project B?
        └─→ PROJECT_B_S3_P4_COLLAB.md
            ├─→ P4_DEPLOYMENT_STRATEGY.md (必读)
            ├─→ TOOLKIT_RESEARCH.md (必读)
            └─→ 参考 eskin_project (架构参考)
```

---

## 💾 工作区文件列表

| 文件 | 类型 | 用途 |
|------|------|------|
| **MASTER_PLAN.md** | 📋 规划 | 总策略与决策指南 |
| **P4_DEPLOYMENT_STRATEGY.md** | 🏗 设计 | 技术细节与编解码方案 |
| **PROJECT_A_S3_PC_INFERENCE.md** | 💻 方案 A | 轻量级原型 |
| **PROJECT_B_S3_P4_COLLAB.md** | 🚀 方案 B | 生产部署 |
| **TOOLKIT_RESEARCH.md** | 🔬 调研 | 工具链评估 |
| **ai_work_flow_prompt.mmd** | 📊 流程 | 工作流图 (旧版) |
| **ai_work_flow_prompt_v2.mmd** | 📊 流程 | 工作流图 (新版，两层架构) |
| **eskin_project/** | 🎹 固件 | 现有 ESP32-S3 MIDI 控制器 |

---

## 🏃 快速行动指南

### 如果我选 Project A：

```bash
# Week 1: 搭建与测试
1. 阅读: PROJECT_A_S3_PC_INFERENCE.md
2. 编码: 复制 eskin_project，删除 BLE/路由层
3. Python: 实现 real_time_inference.py
4. 测试: S3 → USB MIDI → PC → 推理 → 合成器
```

**完成标志**: 可用 S3 弹出旋律，PC 自动生成续写

---

### 如果我选 Project B：

```bash
# Week 1: 基础准备 + 工具链验证
1. 阅读: MASTER_PLAN.md + P4_DEPLOYMENT_STRATEGY.md
2. 安装: esp-idf@v5.2, esp-dl, esp-nn
3. 验证: 模型 INT8 量化是否可行
4. 购置: ESP32-P4 EVB 硬件

# Week 2-3: P4 推理引擎搭建
1. 阅读: PROJECT_B_S3_P4_COLLAB.md (第 3-4 节)
2. 编码: event_lstm.h + uart_protocol.c
3. 测试: P4 单独推理延迟测试

# Week 3-4: S3 + P4 集成
1. 修改: eskin_project → midi_router.h
2. 集成: S3 ↔ P4 UART 通信
3. 测试: 端到端流程验证 (< 150ms 延迟)

# Week 4+: 优化与稳定性
1. 性能分析: 用 esp-ppq 定位瓶颈
2. 优化: 启用 INT8 SIMD (esp-nn)
3. 稳定性: 8+ 小时连续运行测试
```

**完成标志**: 独立系统可工作，可接入合成器或 DAW

---

## 🎓 参考资源

### 官方文档

| 资源 | 链接 |
|------|------|
| ESP-IDF 官方 | https://docs.espressif.com/ |
| esp-dl GitHub | https://github.com/espressif/esp-dl |
| esp-nn GitHub | https://github.com/espressif/esp-nn |
| PyTorch 量化 | https://pytorch.org/docs/stable/quantization.html |

### 我项目中的参考代码

| 目录 | 说明 |
|------|------|
| `eskin_project/src/` | MIDI 事件处理、路由基础 |
| `midi_gen_ai_rewrite/` | Python 模型与生成代码 |
| `libraries/` | Arduino & BLE MIDI 库 |

---

## ❓ 常见问题速查

### Q1: 我应该从哪个项目开始？
**A**: 如果不确定，**先做 Project A (1 周)**，体验完整流程，再考虑 B。

### Q2: Project A/B 可以并行吗？
**A**: 可以。推荐 **Week 1 做 A，Week 2-3 同步做 B**。

### Q3: 需要什么硬件？
**A**: 
- A: ESP32-S3 (已有) + PC
- B: ESP32-S3 (已有) + ESP32-P4 (新购 ~$20)

### Q4: 工具链很复杂吗？
**A**: 不复杂。**TOOLKIT_RESEARCH.md 有完整的 copy-paste 命令**。

### Q5: 最短部署时间是多少？
**A**: A 方案 **4-5 天**，B 方案 **3-4 周** (边学边做)。

### Q6: 量化会降低音乐质量吗？
**A**: 通常 **< 2% 损失**。见 TOOLKIT_RESEARCH 第 4 节的验证方法。

---

## 📝 文档编辑历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1 | 2026-04-11 | 初版发布：5 个技术文档 + 2 个流程图 + 本索引 |

---

## ✨ 接下来的步骤

### 立即行动 (今天)
- [ ] 选择 Project A 或 B
- [ ] 阅读对应的核心文档
- [ ] 列出第一周的具体任务

### 本周内
- [ ] 安装基础工具链 (Python 或 ESP-IDF)
- [ ] 搭建开发环境
- [ ] 跑通第一个 MIDI 输入/输出

### 下周
- [ ] 开始编码 (A: Python | B: C++)
- [ ] 集成硬件测试
- [ ] 收集性能数据

---

## 📞 支持

若有问题，按这个顺序查找答案：

1. **MASTER_PLAN.md** → "常见陷阱与解决方案" 章节
2. **对应 Project 文档** → "故障排查" 或 "Q&A" 表
3. **TOOLKIT_RESEARCH.md** → 工具链特定问题
4. **官方论坛**: GitHub Issues for esp-idf, esp-dl

---

**祝你开发愉快！🎵**


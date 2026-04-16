# ESP-DL 模型部署与测速实验报告

## 目标

在 ESP32-P4 + ESP-IDF + ESP-DL 环境下，把 `midi_gen_ai_rewrite` 里的 `v2_best` 模型部署到 `sample_project`，并获得一个可稳定运行的板端测速结果。

## 结论

最终拿到了一版可稳定运行的“结构等价、兼容优先”的测速模型。它不是原始 checkpoint 的严格推理图，而是为了避免 ESP-DL/ESP-PPQ 兼容性问题而做的等价展开版，但骨架与原模型一致：

- one-hot 输入
- embedding
- 2 层 LSTM 计算
- 输出 head

这版模型已经在板上成功启动、完成推理、打印 profile，并输出平均延迟。

补充说明：当前板端跑的是 8-bit 量化版本，导出时使用了 `num_of_bits=8` 的 ESP-PPQ / ESP-DL 量化流程；但它仍然是兼容优先的等价测速模型，不是原始 checkpoint 的原样业务推理图。

## A/B 复测结果

### 版本A（baseline）

- 配置：`CONFIG_SPIRAM` 关闭，`param_copy=false`
- 平均端到端推理延迟：67.93 ms / 次
- profile 总耗时：68.285 ms
- 应用镜像：`0x26cfa0`

### 版本B（本次复测）

- 配置：`CONFIG_SPIRAM=y`，`param_copy=true`
- 平均端到端推理延迟：34.49165 ms / 次（34491.65 us）
- profile 总耗时：34.891 ms（34891 us）
- 应用镜像：`0x2702e0`
- 模型输出维度：311
- 输出 preview：前 8 个值为 0

### A/B 对比结论

- 端到端延迟减少：33.43835 ms
- 相对加速比：约 1.97x
- 延迟降幅：约 49.2%
- 内存路径变化：版本B中参数副本进入 PSRAM（日志显示 `parameter_copy = 1052.09KB`）

## 板端日志摘要

启动链路正常完成：

- Bootloader 正常加载
- 分区表正常识别
- factory 分区为 7 MB
- 16 MB flash 配置生效
- app_main 成功进入
- 模型成功加载并完成 20 次测量
- benchmark 结束后正常返回

## 结构差异说明

为了避免之前的运行时崩溃，当前板端跑的是“兼容版”模型，而不是原始 checkpoint 的完全一致图。主要差异如下：

- 原模型使用了 `nn.LSTM` 和 `LayerNorm`
- 兼容版把 LSTM 展开成了手写门控计算图，避免 ONNX `LSTM` 兼容问题
- 兼容版移除了 `LayerNorm`，避免触发 `ReduceMean` / `ReduceBase` 断言
- 兼容版使用随机权重，仅用于测速，不用于业务预测
- `main.cpp` 侧模型加载改成了零拷贝参数方式，避免参数深拷贝阶段的内存能力位冲突

## 关键问题与修复

### 1. 模型与业务结构不一致

最早部署的是一个 fallback Conv benchmark，体积只有约 82.5 KB，和真实模型结构差异很大。这个模型只能验证管线，不能代表真实推理速度。后来切回真实 checkpoint 结构，并进一步做兼容化处理。

### 2. ESP-DL / ESP-PPQ 导出兼容问题

遇到过的导出问题包括：

- per-channel quantization 不被运行时支持
- LSTM 对齐阶段 `IndexError`
- 导出器布局阶段 `KeyError: keepdims`

这些问题通过导出脚本热补丁解决，最终完成了可导出的等价模型。

### 3. 运行时内存能力位冲突

模型加载阶段反复出现 `Input cap=0x1000 can not callocate with MALLOC_CAP_SIMD`。

修复过程包括：

- 为 `dl::tool::malloc_aligned` / `calloc_aligned` 增加 fallback
- 让模型加载使用 `param_copy=false`
- 避免参数深拷贝到不兼容的内存区域

### 4. ReduceMean 断言

兼容版最初仍保留了 LayerNorm，导致运行时进入 `ReduceMean` 路径并触发断言。去掉 LayerNorm 后，模型成功跑通。

## 代码修改点

### `main/main.cpp`

- A/B 复测通过切换 `param_copy` 比较两种策略：
	- 版本A：`param_copy=false`（参数留在 flash rodata）
	- 版本B：`param_copy=true`（参数复制到 PSRAM）
- 本报告当前结论基于版本B最新实测

### `managed_components/espressif__esp-dl/dl/tool/src/dl_tool.cpp`

- `malloc_aligned` 和 `calloc_aligned` 增加多级 fallback
- 优先 SIMD 分配，失败后回退到普通分配，再失败后回退到默认堆

### `midi_gen_ai_rewrite/tools/export_v2_best_espdl.py`

- 新增 `EquivalentOneHotEventLSTMLM`
- 用手写展开 LSTM 代替 ONNX `LSTM`
- 新增随机权重测速模式 `--equivalent-random-weights`
- 新增兼容化模式 `--equivalent-unrolled-lstm`
- 关闭 `LayerNorm`，避免 reduce 路径断言
- 强制 legacy ONNX 导出路径，规避 `onnxscript` 兼容问题
- 对 ESP-PPQ 的量化与布局问题做了若干补丁

## 资源与尺寸

- Flash size：16 MB
- Factory app partition：7 MB
- 版本A应用镜像大小：约 0x26cfa0
- 版本B应用镜像大小：约 0x2702e0
- 分区剩余空间：约 65%

## 速度解读

版本A（参数留在 flash）是稳定基线，但延迟显著高于版本B。

版本B（开启 PSRAM + 参数复制）在当前模型上取得了约 1.97x 的加速，且运行稳定、profile 完整，说明“参数副本在 PSRAM”对这版图有明显收益。

因此后续优化建议优先以版本B作为性能基线，再继续做 `SPIRAM_SPEED`、内部内存保留阈值等参数调优。

## 建议

如果目标是最终业务预测：

- 继续尝试让真实 checkpoint 保留更多原始结构
- 或者逐步把当前兼容版替换回原始层，做分阶段对比测速

如果目标只是稳定 benchmark：

- 当前这版已经可以作为可复现的板端测速基线
- 建议固定当前导出脚本和板端加载方式，作为后续优化的对照组

## 备注

本报告记录的是截至当前的稳定运行版本，不包含早期 fallback Conv benchmark 的性能作为最终结果，因为那一版和真实模型结构不一致，参考价值有限。

## 复测索引

- 2026-04-16 复测与可复现记录：`docs/retest_20260416_repro.md`
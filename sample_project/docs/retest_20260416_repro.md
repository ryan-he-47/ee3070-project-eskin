# 2026-04-16 复测与可复现记录

## 目标

在不改动当前成功代码的前提下，重新执行构建和烧录，固化可复现指纹（文件哈希 + 构建产物尺寸）。

## 本次执行

- 使用 ESP-IDF 扩展命令执行 buildFlashMonitor
- 构建完成，刷写成功，设备完成硬复位
- 本次未获取到 monitor 的运行期文本回传（扩展工具回传仅含 build/flash 阶段）

## 构建产物尺寸

- sample_project.bin: 2543520 bytes
- bootloader.bin: 22640 bytes
- partition-table.bin: 3072 bytes

## 关键文件 SHA256

- main/main.cpp: F159309DB1BBB59EEE141ED472A696296ECA3D2BFABDFE6864BAEA8BC2820BDF
- main/models/p4/v2_best.espdl: 0763FEDAEAEEC2E9764618AD48AA255C1F11A6CF5F7A30617F88D562A0FA0CDE
- main/models/p4/v2_best.onnx: F1886D51AA0EDFA61220C875218CCE83E5565B15B0A9C6445A442CF090A6E903
- sdkconfig: 7FB8D7EE0038EE2F7A1DD0A5B499C721FBB8031D3DD4664C9BE66B15734787E5
- partitions.csv: 014BB39E125CBA9C3C2D061C4311456A8254CA785754120134CE7B64D7EB94FE

## 复现检查建议

后续任意一次复测，只要满足下列条件，可认为是同一版基线：

1. 关键文件 SHA256 全部一致
2. sample_project.bin 尺寸仍为 2543520 bytes
3. 分区检查仍显示最小 app 分区 0x700000，空余 65%

## 说明

本记录只新增文档，不覆盖现有源码、模型文件和配置。

## 版本B复测（开启PSRAM + param_copy=true）

### 配置变化

- `sdkconfig`: `CONFIG_SPIRAM=y`
- `main/main.cpp`: `load_model()` 中 `param_copy=true`

### 串口关键结论

- PSRAM识别并通过测试：32MB，`memory test OK`
- 平均端到端延迟：`34491.65 us`（20次）
- profile总耗时：`34891 us`
- 模型内存摘要显示：`parameter_copy = 1052.09KB`（位于 PSRAM）
- 运行完成并正常返回：`Benchmark finished`

### 构建产物尺寸（版本B）

- sample_project.bin: 2556640 bytes
- bootloader.bin: 22640 bytes
- partition-table.bin: 3072 bytes

### 关键文件 SHA256（版本B）

- main/main.cpp: BA67BC7A9D0665A989CB81A678202E5C8BBF3B0FE693BDDE384B6CD30D002CF8
- main/models/p4/v2_best.espdl: 0763FEDAEAEEC2E9764618AD48AA255C1F11A6CF5F7A30617F88D562A0FA0CDE
- main/models/p4/v2_best.onnx: F1886D51AA0EDFA61220C875218CCE83E5565B15B0A9C6445A442CF090A6E903
- sdkconfig: B653FF516366A1581382762424A8F3BF9E6B7F9C7C4A26A73A49D77A86468A2F
- partitions.csv: 014BB39E125CBA9C3C2D061C4311456A8254CA785754120134CE7B64D7EB94FE

## 三档内部SRAM扫描补充

你后面贴出来的是 192 KiB 和 256 KiB 两档，128 KiB 那一档的串口记录已经丢失，所以这里只能先给出后两档的可核实结果：

| max_internal_size | 平均延迟 | profile总耗时 | internal RAM变量区 |
| --- | ---: | ---: | ---: |
| 192 KiB | 34198.40 us | 34514 us | 192.00 KiB |
| 256 KiB | 34228.55 us | 34542 us | 256.00 KiB |

### 结论

- 192 KiB 和 256 KiB 的延迟几乎持平，差值只有 30.15 us，属于噪声级别。
- 把内部 SRAM 上限从 192 KiB 继续拉到 256 KiB，没有带来可见性能收益，只增加了内部 RAM 占用。
- 从这两档来看，192 KiB 已经基本够用；若要继续找最优点，重点应回头补 128 KiB 那档再对照。
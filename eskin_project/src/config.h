#ifndef CFG_CONFIG_H
#define CFG_CONFIG_H

#include "src/pressure_process.h"   // 包含 KeyConfig 定义

// 配置数量（可根据需要调整）
extern const int NUM_CONFIGS;
// 配置数组，外部可访问
extern KeyConfig configs[];
// 当前使用的配置索引
extern int currentConfig;

// 初始化所有配置（在 setup 中调用一次）
void initAllConfigs();

#endif
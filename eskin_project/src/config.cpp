#include "config.h"

// 定义配置数量
const int NUM_CONFIGS = 3;

// 定义配置数组（注意：这里只是声明空间，实际内容在 initAllConfigs 中填充）
KeyConfig configs[NUM_CONFIGS];

// 当前配置索引
int currentConfig = -1; // -1 表示未选择任何配置

// 初始化所有配置的具体参数
void initAllConfigs() {
    // ========== 配置 0：钢琴模式 ==========
    uint8_t whiteKeys[16] ={0,0,2,2,4,4,5,5,7,7,9,9,11,11,12,12};//白键音高偏移 
    uint8_t blackKeys[16] ={0,1,1,3,3,4,4,6,6,8,8,10,10,11,11,13};//黑键音高偏移
    KeyType whiteKeyType[16]={KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION};
    KeyType blackKeyType[16]={KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION};
     for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[0].keyTypeMap[r][c] =KeyType::NO_FUNCTION;
            configs[0].trigThreshMap[r][c] = 40;
            if(r==14){
                configs[0].trigThreshMap[r][c] = 50;
            } 
            }
            
        }
    for (int c = 0; c < MATRIX_COLS; c++) {
        configs[0].pitchMap[14][c] = whiteKeys[c]+48;
        configs[0].pitchMap[12][c] = blackKeys[c]+48;
        configs[0].pitchMap[10][c] = whiteKeys[c]+60;
        configs[0].pitchMap[8][c] = blackKeys[c]+60;
        configs[0].pitchMap[6][c] = whiteKeys[c]+72;
        configs[0].pitchMap[4][c] = blackKeys[c]+72;
        configs[0].pitchMap[2][c] = whiteKeys[c]+84;
        configs[0].pitchMap[0][c] = blackKeys[c]+84;


        configs[0].keyTypeMap[14][c] = whiteKeyType[c];
        configs[0].keyTypeMap[12][c] = blackKeyType[c];
        configs[0].keyTypeMap[10][c] = whiteKeyType[c];
        configs[0].keyTypeMap[8][c] = blackKeyType[c];
        configs[0].keyTypeMap[6][c] = whiteKeyType[c];
        configs[0].keyTypeMap[4][c] = blackKeyType[c];
        configs[0].keyTypeMap[2][c] = whiteKeyType[c];
        configs[0].keyTypeMap[0][c] = blackKeyType[c];
    
    }
    
    
    

    // ========== 配置 1： ==========
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[1].keyTypeMap[r][c] = KeyType::BASIC_INSTRUMENT;
            configs[1].trigThreshMap[r][c] = 37;
            configs[1].pitchMap[r][c] = r * 16 + c;
            configs[1].channelMap[r][c] = 1;
        }
    }

    // ========== 配置 2： ==========
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[2].keyTypeMap[r][c] = KeyType::PIANO;
            configs[2].trigThreshMap[r][c] = 37;
            configs[2].pitchMap[r][c] = r * 16 + c;
            configs[2].channelMap[r][c] = 1;
        }
    }
}
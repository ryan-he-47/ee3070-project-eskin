#include "config.h"

// 定义配置数量
const int NUM_CONFIGS = 6;

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
            configs[0].trigThreshMap[r][c] = 37;
            if(r==14){
                configs[0].trigThreshMap[r][c] = 47;
            } 

            }
            configs[0].channelPC[r]=0;
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
            configs[1].keyTypeMap[r][c] = KeyType::NO_FUNCTION;
            configs[1].trigThreshMap[r][c] = 37;
            configs[1].pitchMap[r][c] = r * 16 + c;
            configs[1].channelMap[r][c] = 1;
        }
        configs[1].channelPC[r]=40;
    }
    configs[1].keyTypeMap[0][0] = KeyType::SINGLE_POINT;//左上角特殊功能键







    // ========== 配置 2： ==========
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[2].keyTypeMap[r][c] = KeyType::BASIC_MPE;
            configs[2].trigThreshMap[r][c] = 40;
            configs[2].pitchMap[r][c] = r + c+48;
            configs[2].channelMap[r][c] = 1;
        }
    }


    // ========== 配置 3：violin ==========
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[3].keyTypeMap[r][c] = KeyType::NO_FUNCTION;
            configs[3].trigThreshMap[r][c] = 40;
            configs[3].channelMap[r][c] = 1;
        }
        configs[3].channelPC[r]=40;
    }
    configs[3].keyTypeMap[15][0] = KeyType::VIOLIN;
    configs[3].keyTypeMap[15][4] = KeyType::VIOLIN;
    configs[3].keyTypeMap[15][8] = KeyType::VIOLIN;
    configs[3].keyTypeMap[15][12] = KeyType::VIOLIN;
    configs[3].pitchMap[15][0] = 55+3;
    configs[3].pitchMap[15][4] = 62+3;
    configs[3].pitchMap[15][8] = 69+3;
    configs[3].pitchMap[15][12] = 76+3;


    // ========== 配置 4： ==========
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[4].keyTypeMap[r][c] = KeyType::DRUM;
            configs[4].trigThreshMap[r][c] = 40;
            configs[4].channelMap[r][c] = 1;
        }
        configs[4].channelPC[r]=38;
    }

    // ========== 配置 5： ==========
    KeyType whiteKeyType2[16]={KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION};
    KeyType blackKeyType2[16]={KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::PIANO,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION,KeyType::NO_FUNCTION};
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            configs[5].keyTypeMap[r][c] = KeyType::NO_FUNCTION;
            configs[5].trigThreshMap[r][c] = 40;
            if(c>=12){
                configs[5].channelMap[r][c] = 2;
            }else if(c<12){
            configs[5].channelMap[r][c] = 3;
            }
        }
        configs[5].channelPC[r]=73;
    }

    configs[5].channelPC[2]=40;//violin
    configs[5].channelPC[3]=0;//piano



    for (int c = 0; c < MATRIX_COLS; c++) {


        configs[5].pitchMap[6][c] = whiteKeys[c]+72;
        configs[5].pitchMap[4][c] = blackKeys[c]+72;
        configs[5].pitchMap[2][c] = whiteKeys[c]+84;
        configs[5].pitchMap[0][c] = blackKeys[c]+84;


        configs[5].keyTypeMap[6][c] = whiteKeyType2[c];
        configs[5].keyTypeMap[4][c] = blackKeyType2[c];
        configs[5].keyTypeMap[2][c] = whiteKeyType2[c];
        configs[5].keyTypeMap[0][c] = blackKeyType2[c];
    
    }

    configs[5].keyTypeMap[15][12] = KeyType::VIOLIN;
    configs[5].pitchMap[15][12] = 62+3;
    
    for (int r = 8; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < 12; c++) {
            configs[5].keyTypeMap[r][c] = KeyType::BASIC_MPE;
            configs[5].pitchMap[r][c] = r + c + 48;
        }
    }


}
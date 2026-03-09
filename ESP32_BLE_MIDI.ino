/**
 * @file    main.cpp
 * @brief   ESP32 DevKit-32E  —  BLE MIDI via FreeRTOS 队列
 *
 * 架构
 * ────
 *  ┌─────────────────────┐      MidiEvent 队列       ┌──────────────────────┐
 *  │  midi_debug_task    │ ──── xMidiQueue ────────► │  ble_midi_send_task  │
 *  │  (调试/事件生产者)   │                           │  (BLE MIDI 发送)     │
 *  └─────────────────────┘                           └──────────────────────┘
 *
 * 说明
 * ────
 *  • midi_debug_task  每隔 1 s 向队列写入一条示例 MIDI 事件（NoteOn / NoteOff
 *    交替），用于在没有外部 MIDI 硬件的情况下验证整条链路。
 *  • ble_midi_send_task 阻塞等待队列，收到事件后通过 ESP32-BLE-MIDI 库把
 *    标准 BLE MIDI 1.0 数据包发送出去，可被 macOS / iOS GarageBand 识别。
 *  • 两个任务均固定在 Core 1，避免 BLE 栈（Core 0）产生干扰。
 *
 * 依赖
 * ────
 *  lathoub/ESP32-BLE-MIDI  (platformio lib_deps 已配置)
 */

#include <Arduino.h>
#include <BLEMidi.h>   // lathoub/ESP32-BLE-MIDI

// ═══════════════════════════════════════════════════════════════════════════
//  MIDI 事件结构体
// ═══════════════════════════════════════════════════════════════════════════

/**
 * MidiEventType  —  支持的 MIDI 事件类型
 * 可根据需要继续扩展（ControlChange、PitchBend 等）
 */
enum class MidiEventType : uint8_t {
    NoteOn       = 0x90,
    NoteOff      = 0x80,
    ControlChange = 0xB0,
    ProgramChange = 0xC0,
    PitchBend    = 0xE0,
};

/**
 * MidiEvent  —  在任务间通过队列传递的 MIDI 事件
 *
 * 字段说明
 *   type     : 事件类型（见 MidiEventType）
 *   channel  : MIDI 通道 0–15（对应 MIDI Ch.1–16）
 *   data1    : 音符编号 / 控制器编号 / 程序编号 / Pitch LSB
 *   data2    : 力度 / 控制器值 / Pitch MSB（ProgramChange 时忽略）
 */
struct MidiEvent {
    MidiEventType type;
    uint8_t       channel;
    uint8_t       data1;
    uint8_t       data2;
};

// ═══════════════════════════════════════════════════════════════════════════
//  全局句柄
// ═══════════════════════════════════════════════════════════════════════════

static QueueHandle_t xMidiQueue = nullptr;

// BLE MIDI 连接状态标志（在回调中更新，用 volatile 保证可见性）
static volatile bool bleConnected = false;

// ═══════════════════════════════════════════════════════════════════════════
//  BLE MIDI 回调
// ═══════════════════════════════════════════════════════════════════════════

static void onBleConnect() {
    bleConnected = true;
    Serial.println("[BLE] 设备已连接");
}

static void onBleDisconnect() {
    bleConnected = false;
    Serial.println("[BLE] 设备已断开");
}

// ═══════════════════════════════════════════════════════════════════════════
//  任务：midi_debug_task  （调试 / 事件生产者）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 每隔 DEBUG_INTERVAL_MS 毫秒向队列发送一条 NoteOn/NoteOff 交替事件。
 * 实际项目中，可将此任务替换为从串口、UART MIDI、触摸传感器等来源
 * 读取真实 MIDI 事件，然后 xQueueSend 到 xMidiQueue。
 */
static const uint32_t DEBUG_INTERVAL_MS = 1000;   // 调试发送间隔
static const uint8_t  DEBUG_CHANNEL     = 0;      // MIDI Ch.1
static const uint8_t  DEBUG_NOTE        = 60;     // Middle C
static const uint8_t  DEBUG_VELOCITY    = 100;

static void midi_debug_task(void* /*pvParameters*/) {
    Serial.println("[DEBUG TASK] 已启动");

    bool noteIsOn = false;

    while (true) {
        MidiEvent evt;
        evt.channel = DEBUG_CHANNEL;
        evt.data1   = DEBUG_NOTE;

        if (!noteIsOn) {
            evt.type  = MidiEventType::NoteOn;
            evt.data2 = DEBUG_VELOCITY;
            Serial.printf("[DEBUG TASK] → NoteOn  ch=%u note=%u vel=%u\n",
                          evt.channel, evt.data1, evt.data2);
        } else {
            evt.type  = MidiEventType::NoteOff;
            evt.data2 = 0;
            Serial.printf("[DEBUG TASK] → NoteOff ch=%u note=%u\n",
                          evt.channel, evt.data1);
        }
        noteIsOn = !noteIsOn;

        // 发送到队列；若队列满则丢弃当前事件（0 tick = 非阻塞）
        if (xQueueSend(xMidiQueue, &evt, 0) != pdTRUE) {
            Serial.println("[DEBUG TASK] 警告：队列已满，事件被丢弃");
        }

        vTaskDelay(pdMS_TO_TICKS(DEBUG_INTERVAL_MS));
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  辅助：将 MidiEvent 通过 BLE MIDI 发送出去
// ═══════════════════════════════════════════════════════════════════════════

static void sendMidiEvent(const MidiEvent& evt) {
    switch (evt.type) {
        case MidiEventType::NoteOn:
            BLEMidiServer.noteOn(evt.channel, evt.data1, evt.data2);
            Serial.printf("[BLE SEND] NoteOn  ch=%u note=%u vel=%u\n",
                          evt.channel, evt.data1, evt.data2);
            break;

        case MidiEventType::NoteOff:
            BLEMidiServer.noteOff(evt.channel, evt.data1, evt.data2);
            Serial.printf("[BLE SEND] NoteOff ch=%u note=%u vel=%u\n",
                          evt.channel, evt.data1, evt.data2);
            break;

        case MidiEventType::ControlChange:
            BLEMidiServer.controlChange(evt.channel, evt.data1, evt.data2);
            Serial.printf("[BLE SEND] CC      ch=%u cc=%u val=%u\n",
                          evt.channel, evt.data1, evt.data2);
            break;

        case MidiEventType::ProgramChange:
            BLEMidiServer.programChange(evt.channel, evt.data1);
            Serial.printf("[BLE SEND] PC      ch=%u prog=%u\n",
                          evt.channel, evt.data1);
            break;

        case MidiEventType::PitchBend: {
            // data1 = LSB (0–127), data2 = MSB (0–127)
            // BLE MIDI pitchBend 期望 -8192~8191
            int pitchVal = (int)(((uint16_t)evt.data2 << 7) | evt.data1) - 8192;
            BLEMidiServer.pitchBend(evt.channel, (uint16_t)pitchVal);
            Serial.printf("[BLE SEND] PitchBend ch=%u val=%d\n",
                          evt.channel, pitchVal);
            break;
        }

        default:
            Serial.printf("[BLE SEND] 未知事件类型: 0x%02X\n",
                          static_cast<uint8_t>(evt.type));
            break;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  任务：ble_midi_send_task  （BLE MIDI 发送）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 阻塞等待 xMidiQueue 中的事件。
 * 若 BLE 尚未连接，则将事件记录到串口并丢弃（避免 BLE 库在未连接时崩溃）。
 * 连接后实时转发。
 */
static void ble_midi_send_task(void* /*pvParameters*/) {
    Serial.println("[BLE TASK] 已启动，等待 BLE 连接...");

    MidiEvent evt;

    while (true) {
        // 永久阻塞直到队列有数据
        if (xQueueReceive(xMidiQueue, &evt, portMAX_DELAY) == pdTRUE) {
            if (bleConnected) {
                sendMidiEvent(evt);
            } else {
                // BLE 未连接时仅打印，不丢失结构信息
                Serial.printf("[BLE TASK] BLE 未连接，丢弃事件 type=0x%02X "
                              "ch=%u d1=%u d2=%u\n",
                              static_cast<uint8_t>(evt.type),
                              evt.channel, evt.data1, evt.data2);
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  setup / loop
// ═══════════════════════════════════════════════════════════════════════════

void setup() {
    Serial.begin(115200);
    delay(500);  // 等待串口监视器就绪
    Serial.println("\n=== ESP32 BLE MIDI (DevKit-32E) ===");

    // ── 1. 创建 MIDI 事件队列（深度 32） ──────────────────────────────────
    xMidiQueue = xQueueCreate(32, sizeof(MidiEvent));
    if (xMidiQueue == nullptr) {
        Serial.println("[FATAL] 队列创建失败，程序停止");
        while (true) { vTaskDelay(pdMS_TO_TICKS(1000)); }
    }
    Serial.println("[INIT] MIDI 事件队列已创建（深度 32）");

    // ── 2. 初始化 BLE MIDI Server ─────────────────────────────────────────
    //   设备名称需与 GarageBand 搜索的蓝牙名称对应，可自定义。
    //   GarageBand 会扫描所有符合 BLE MIDI 规范的设备（MIDI over BLE，
    //   Apple 的 CoreMIDI 网络会话协议，Service UUID: 03B80E5A-EDE8-4B33-A751-6CE34EC4C700）
    BLEMidiServer.begin("ESP32-MIDI");
    BLEMidiServer.setOnConnectCallback(onBleConnect);
    BLEMidiServer.setOnDisconnectCallback(onBleDisconnect);
    Serial.println("[INIT] BLE MIDI Server 已启动，设备名: ESP32-MIDI");

    // ── 3. 创建 FreeRTOS 任务 ─────────────────────────────────────────────
    //   两个任务均分配在 Core 1（BLE 协议栈默认运行在 Core 0）
    xTaskCreatePinnedToCore(
        midi_debug_task,    // 任务函数
        "midi_debug",       // 任务名（调试用）
        4096,               // 栈大小（字节）
        nullptr,            // 参数
        1,                  // 优先级
        nullptr,            // 任务句柄（不需要保存）
        1                   // Core ID
    );

    xTaskCreatePinnedToCore(
        ble_midi_send_task,
        "ble_midi_send",
        4096,
        nullptr,
        2,                  // 发送任务优先级略高，确保实时性
        nullptr,
        1
    );

    Serial.println("[INIT] 所有任务已创建，进入主循环");
}

void loop() {
    // 所有逻辑均在 FreeRTOS 任务中运行，loop 仅负责喂狗 / 状态打印
    static uint32_t lastPrint = 0;
    uint32_t now = millis();
    if (now - lastPrint >= 5000) {
        lastPrint = now;
        Serial.printf("[LOOP] 运行中... BLE 连接状态: %s\n",
                      bleConnected ? "已连接" : "未连接");
    }
    vTaskDelay(pdMS_TO_TICKS(100));
}

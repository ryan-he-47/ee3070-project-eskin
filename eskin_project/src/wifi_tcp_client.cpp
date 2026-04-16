#include "wifi_tcp_client.h"
#include "src/pressure_process.h"
#include "src/USBMIDI1.h"
#include "src/BLEMidi.h"

// ===== 全局变量定义 =====
const char* WIFI_SSID     = "GX8CR5S1";       // 替换为你的 WiFi SSID
const char* WIFI_PASSWORD = "12345678";       // 替换为你的 WiFi 密码
const char* SERVER_IP     = "192.168.137.1";      // 替换为 Windows PC 的 IP 地址
const int   SERVER_PORT   = 8888;                 // 与 Python 脚本端口一致

WiFiClient client;
bool connectFlag = false;

// 重连控制
unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL = 3000; // 3秒重连一次

// 接收缓冲区
String receiveBuffer = "";

// ===== 函数实现 =====

// ---- WiFi 连接 ----
void connectWiFi() {
    Serial.printf("[WiFi] 正在连接到 %s ...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        vTaskDelay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.println("[WiFi] 连接成功！");
        Serial.printf("[WiFi] IP 地址: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[WiFi] 信号强度 (RSSI): %d dBm\n", WiFi.RSSI());
    } else {
        Serial.println();
        Serial.println("[WiFi] 连接失败，将在5秒后重试...");
    }
}

// ---- 连接 TCP Server ----
void connectToServer() {
    // Ensure stale sockets are cleaned up before re-trying a TCP connect.
    client.stop();

    IPAddress serverAddr;
    bool serverIpOk = serverAddr.fromString(SERVER_IP);
    Serial.printf("[TCP] 正在连接到服务器 %s:%d ...\n", SERVER_IP, SERVER_PORT);
    Serial.printf("[TCP] 本机IP=%s 网关=%s\n", WiFi.localIP().toString().c_str(), WiFi.gatewayIP().toString().c_str());
    if (!serverIpOk) {
        Serial.printf("[TCP] 错误: SERVER_IP 非法: %s\n", SERVER_IP);
        return;
    }
    
    if (client.connect(serverAddr, SERVER_PORT)) {
        Serial.println("[TCP] 连接成功！");
        sendMessage("HELLO:ESP32已连接,IP=" + WiFi.localIP().toString());
    } else {
        Serial.println("[TCP] 连接失败，将重试...");
    }
}

// ---- 发送消息 ----
void sendMessage(String msg) {
    if (client.connected()) {
        client.println(msg);  // println 会自动添加 \r\n
        //Serial.printf("[ESP32 -> PC] %s\n", msg.c_str());
    } else {
        Serial.println("[发送失败] TCP 未连接");
    }
}

void sendMIDIFrame(const uint8_t frame[3]) {
    if (!client.connected()) {
        return;
    }
    client.printf("MIDI:%u,%u,%u\n", frame[0], frame[1], frame[2]);
}

static bool decodeMIDIFrame(uint8_t status, uint8_t data1, uint8_t data2, MIDIEvent &event) {
    uint8_t type = status & 0xF0;
    uint8_t channel = (status & 0x0F) + 1;
    event.channel = channel;
    event.data1 = data1 & 0x7F;
    event.data2 = data2 & 0x7F;
    event.MPEnote = 128;

    switch (type) {
        case 0x90:
            event.type = (event.data2 == 0) ? MIDIEventType::NoteOff : MIDIEventType::NoteOn;
            return true;
        case 0x80:
            event.type = MIDIEventType::NoteOff;
            return true;
        case 0xB0:
            event.type = MIDIEventType::ControlChange;
            return true;
        case 0xC0:
            event.type = MIDIEventType::ProgramChange;
            return true;
        case 0xD0:
            event.type = MIDIEventType::ChannelAT;
            return true;
        case 0xE0:
            event.type = MIDIEventType::PitchBend;
            return true;
        default:
            return false;
    }
}


// ---- 接收并解析来自 Windows 的数据 ----
void receiveData() {
    while (client.available()) {
        char c = client.read();
        if (c == '\n') {
            receiveBuffer.trim();
            if (receiveBuffer.length() > 0) {
                processCommand(receiveBuffer);
            }
            receiveBuffer = "";
        } else if (c != '\r') {
            receiveBuffer += c;
        }
    }
}

// ---- 处理收到的指令的示例 ----
void processCommand(String cmd) {
    Serial.printf("[PC -> ESP32] 收到指令: %s\n", cmd.c_str());

    if (cmd.startsWith("MIDI:")) {
        int p1 = cmd.indexOf(',', 5);
        int p2 = (p1 == -1) ? -1 : cmd.indexOf(',', p1 + 1);
        if (p1 > 5 && p2 > p1) {
            uint8_t b0 = (uint8_t)cmd.substring(5, p1).toInt();
            uint8_t b1 = (uint8_t)cmd.substring(p1 + 1, p2).toInt();
            uint8_t b2 = (uint8_t)cmd.substring(p2 + 1).toInt();
            MIDIEvent evt;
            if (decodeMIDIFrame(b0, b1, b2, evt)) {
                usbMidiSendEvent(evt);
                bleMidiSendEvent(evt);
            }
        }
        return;
    }
    
    // 指令解析示例
    if (cmd == "LED_ON") {
        digitalWrite(2, HIGH);  // 点亮板载 LED（GPIO2）
        sendMessage("ACK:LED已打开");
        
    } else if (cmd == "LED_OFF") {
        digitalWrite(2, LOW);   // 关闭板载 LED
        sendMessage("ACK:LED已关闭");
        
    } else if (cmd == "STATUS") {
        // 返回设备状态
        String status = "STATUS:IP=" + WiFi.localIP().toString() 
                      + ",RSSI=" + String(WiFi.RSSI()) 
                      + ",Uptime=" + String(millis()/1000) + "s";
        sendMessage(status);
        
    } else if (cmd.startsWith("GPIO:")) {
        // 格式: GPIO:引脚号:状态  例如: GPIO:5:1
        int firstColon = cmd.indexOf(':', 5);
        if (firstColon != -1) {
            int pin = cmd.substring(5, firstColon).toInt();
            int state = cmd.substring(firstColon + 1).toInt();
            pinMode(pin, OUTPUT);
            digitalWrite(pin, state);
            sendMessage("ACK:GPIO" + String(pin) + "=" + String(state));
        }
        
    } else if (cmd == "RESTART") {
        sendMessage("ACK:ESP32即将重启");
        vTaskDelay(500);
        ESP.restart();
        
    } else {
        // 未知指令，回传
        sendMessage("UNKNOWN:" + cmd);
    }
}

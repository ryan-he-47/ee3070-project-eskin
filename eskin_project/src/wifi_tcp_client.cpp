#include "wifi_tcp_client.h"

// ===== 全局变量定义 =====
const char* WIFI_SSID     = "DESKTOP-98FU7II 5494";       // 替换为你的 WiFi SSID
const char* WIFI_PASSWORD = "123698745";       // 替换为你的 WiFi 密码
const char* SERVER_IP     = "10.10.71.46";      // 替换为 Windows PC 的 IP 地址
const int   SERVER_PORT   = 8888;                 // 与 Python 脚本端口一致

WiFiClient client;
bool connectFlag = false;

// 重连控制
unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL = 5000; // 5秒重连一次

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
    Serial.printf("[TCP] 正在连接到服务器 %s:%d ...\n", SERVER_IP, SERVER_PORT);
    
    if (client.connect(SERVER_IP, SERVER_PORT)) {
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

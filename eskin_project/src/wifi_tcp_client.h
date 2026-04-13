#ifndef WIFI_TCP_CLIENT_H
#define WIFI_TCP_CLIENT_H

#include <WiFi.h>
#include <ArduinoJson.h>

// ===== 必须修改的配置区域 =====
extern const char* WIFI_SSID;       // WiFi SSID
extern const char* WIFI_PASSWORD;   // WiFi 密码
extern const char* SERVER_IP;       // 服务器 IP 地址
extern const int   SERVER_PORT;     // 服务器端口
// ================================

extern WiFiClient client;
extern bool connectFlag;

extern const int LED_PIN;

// 重连控制
extern unsigned long lastReconnectAttempt;
extern const unsigned long RECONNECT_INTERVAL;

// 心跳控制
extern unsigned long lastHeartbeat;
extern const unsigned long HEARTBEAT_INTERVAL;

// 传感器数据发送间隔
extern unsigned long lastSensorSend;
extern const unsigned long SENSOR_INTERVAL;

// 接收缓冲区
extern String receiveBuffer;

// 函数声明
void connectWiFi();
void connectToServer();
void sendMessage(String msg);
void sendSensorData();
void receiveData();
void processCommand(String cmd);

#endif

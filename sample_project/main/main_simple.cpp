#include "esp_log.h"

static const char *TAG = "test";

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "Hello from ESP32!");
}

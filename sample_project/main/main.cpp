#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <map>

#include "dl_model_base.hpp"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "v2_best_benchmark";

#if defined(USE_EMBEDDED_ESPDL_MODEL) && USE_EMBEDDED_ESPDL_MODEL
extern const uint8_t v2_best_espdl[] asm("_binary_v2_best_espdl_start");
#endif

template <typename T>
static void fill_tensor(dl::TensorBase *tensor)
{
    T *data = tensor->get_element_ptr<T>();
    std::fill_n(data, tensor->size, static_cast<T>(0));
    if (tensor->size > 0) {
        data[0] = static_cast<T>(1);
    }
}

static void print_tensor_preview(dl::TensorBase *tensor, const char *label)
{
    if (tensor == nullptr) {
        ESP_LOGW(TAG, "%s: tensor is null", label);
        return;
    }

    const size_t preview_count = std::min<size_t>(8, tensor->size);
    ESP_LOGI(TAG, "%s: dtype=%d size=%u", label, static_cast<int>(tensor->get_dtype()), static_cast<unsigned>(tensor->size));

    if (tensor->get_dtype() == dl::DATA_TYPE_INT8) {
        const int8_t *data = tensor->get_element_ptr<int8_t>();
        printf("%s preview:", label);
        for (size_t i = 0; i < preview_count; ++i) {
            printf(" %d", static_cast<int>(data[i]));
        }
        printf("\n");
    } else if (tensor->get_dtype() == dl::DATA_TYPE_INT16) {
        const int16_t *data = tensor->get_element_ptr<int16_t>();
        printf("%s preview:", label);
        for (size_t i = 0; i < preview_count; ++i) {
            printf(" %d", static_cast<int>(data[i]));
        }
        printf("\n");
    } else {
        const float *data = tensor->get_element_ptr<float>();
        printf("%s preview:", label);
        for (size_t i = 0; i < preview_count; ++i) {
            printf(" %.6f", static_cast<double>(data[i]));
        }
        printf("\n");
    }
}

static dl::Model *load_model()
{
#if defined(USE_EMBEDDED_ESPDL_MODEL) && USE_EMBEDDED_ESPDL_MODEL
    return new dl::Model((const char *)v2_best_espdl,
                         fbs::MODEL_LOCATION_IN_FLASH_RODATA,
                         0,
                         dl::MEMORY_MANAGER_GREEDY,
                         nullptr,
                         true);
#else
    return new dl::Model("/sdcard/v2_best.espdl",
                         fbs::MODEL_LOCATION_IN_SDCARD,
                         0,
                         dl::MEMORY_MANAGER_GREEDY,
                         nullptr,
                         true);
#endif
}

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "Starting v2_best ESP-DL inference benchmark");
#if !(defined(USE_EMBEDDED_ESPDL_MODEL) && USE_EMBEDDED_ESPDL_MODEL)
    ESP_LOGI(TAG, "Expected model path: /sdcard/v2_best.espdl");
#endif

    dl::Model *model = load_model();
    if (model == nullptr) {
        ESP_LOGE(TAG, "Failed to construct model");
        return;
    }

    std::map<std::string, dl::TensorBase *> inputs = model->get_inputs();
    if (inputs.empty()) {
        ESP_LOGE(TAG, "Model has no inputs");
        delete model;
        return;
    }

    dl::TensorBase *input_tensor = inputs.begin()->second;
    if (input_tensor->get_dtype() == dl::DATA_TYPE_INT8) {
        fill_tensor<int8_t>(input_tensor);
    } else if (input_tensor->get_dtype() == dl::DATA_TYPE_INT16) {
        fill_tensor<int16_t>(input_tensor);
    } else {
        fill_tensor<float>(input_tensor);
    }

    constexpr int warmup_runs = 5;
    constexpr int measure_runs = 20;

    for (int i = 0; i < warmup_runs; ++i) {
        model->run(input_tensor);
    }

    int64_t total_us = 0;
    for (int i = 0; i < measure_runs; ++i) {
        int64_t start_us = esp_timer_get_time();
        model->run(input_tensor);
        total_us += esp_timer_get_time() - start_us;
    }

    const double average_us = static_cast<double>(total_us) / static_cast<double>(measure_runs);
    ESP_LOGI(TAG, "Average end-to-end inference latency: %.2f us over %d runs", average_us, measure_runs);

    std::map<std::string, dl::TensorBase *> outputs = model->get_outputs();
    if (!outputs.empty()) {
        print_tensor_preview(outputs.begin()->second, "output");
    }

    model->profile();
    delete model;
    ESP_LOGI(TAG, "Benchmark finished");
}
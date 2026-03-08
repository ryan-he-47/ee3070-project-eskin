import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib

matplotlib.use('TkAgg')

# -------------------------- 配置参数 --------------------------
SERIAL_PORT = 'COM8'  # 你的串口端口
BAUD_RATE = 115200  # 波特率与ESP32一致
TIMEOUT = 1  # 串口超时时间

# 帧头定义（区分矩阵和字符串）
HEADER_MATRIX = b'\x00\x10\x11\x20'  # 矩阵帧头（与ESP32一致）
HEADER_STRING = b'\x01\x02\x30\x22'  # 字符串帧头（新增）

# 数据长度定义
FRAME_SIZE_MATRIX = 256  # 16x16矩阵字节数
FRAME_SIZE_STRING_LEN = 2  # 字符串长度字段（2字节uint16_t）

# -------------------------- 初始化 --------------------------
# 串口初始化
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=TIMEOUT)
# 全局缓冲区（存储未解析的串口数据）
buffer = bytearray()

# 绘图初始化
fig, ax = plt.subplots()
im = ax.imshow(np.zeros((16, 16)), cmap='hot', interpolation='nearest', vmin=0, vmax=255)
plt.colorbar(im)
ax.set_title("Pressure Matrix (Real-time)")


# -------------------------- 核心解析函数 --------------------------
def update(frame):
    global buffer
    # 1. 读取串口所有可用数据并追加到缓冲区
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        buffer.extend(data)

    # 2. 循环解析缓冲区中的帧（优先处理先出现的帧）
    while True:
        # 查找两个帧头的位置
        idx_matrix = buffer.find(HEADER_MATRIX)
        idx_string = buffer.find(HEADER_STRING)

        # 确定当前需要处理的帧类型（选位置更小的帧头，-1表示未找到）
        process_matrix = False
        process_string = False
        current_idx = -1

        # 情况1：只有矩阵帧头
        if idx_matrix != -1 and idx_string == -1:
            process_matrix = True
            current_idx = idx_matrix
        # 情况2：只有字符串帧头
        elif idx_string != -1 and idx_matrix == -1:
            process_string = True
            current_idx = idx_string
        # 情况3：两个帧头都存在，处理先出现的
        elif idx_matrix != -1 and idx_string != -1:
            if idx_matrix < idx_string:
                process_matrix = True
                current_idx = idx_matrix
            else:
                process_string = True
                current_idx = idx_string
        # 情况4：无帧头，清理缓冲区（保留最后3字节，防止帧头跨包）
        else:
            if len(buffer) > max(len(HEADER_MATRIX), len(HEADER_STRING)) - 1:
                buffer = buffer[-(max(len(HEADER_MATRIX), len(HEADER_STRING)) - 1):]
            break

        # -------------------------- 处理矩阵帧 --------------------------
        if process_matrix:
            # 检查是否有完整的矩阵帧数据
            if len(buffer) >= current_idx + len(HEADER_MATRIX) + FRAME_SIZE_MATRIX:
                # 提取矩阵数据
                matrix_bytes = buffer[current_idx + len(HEADER_MATRIX):
                                      current_idx + len(HEADER_MATRIX) + FRAME_SIZE_MATRIX]
                matrix = np.frombuffer(matrix_bytes, dtype=np.uint8).reshape((16, 16))
                # 更新绘图
                im.set_data(matrix)
                ax.set_title(f"Pressure Matrix (Frame {frame})")
                # 移除已处理的数据
                buffer = buffer[current_idx + len(HEADER_MATRIX) + FRAME_SIZE_MATRIX:]
            else:
                # 数据不足，等待下一次更新
                break

        # -------------------------- 处理字符串帧 --------------------------
        elif process_string:
            # 检查是否有至少“帧头+长度字段”的数据
            if len(buffer) >= current_idx + len(HEADER_STRING) + FRAME_SIZE_STRING_LEN:
                # 提取字符串长度（2字节，小端模式，与ESP32匹配）
                str_len_bytes = buffer[current_idx + len(HEADER_STRING):
                                       current_idx + len(HEADER_STRING) + FRAME_SIZE_STRING_LEN]
                str_len = np.frombuffer(str_len_bytes, dtype=np.uint16)[0]  # 小端解析

                # 检查是否有完整的字符串数据
                if len(buffer) >= current_idx + len(HEADER_STRING) + FRAME_SIZE_STRING_LEN + str_len:
                    # 提取字符串字节并解码
                    str_bytes = buffer[current_idx + len(HEADER_STRING) + FRAME_SIZE_STRING_LEN:
                                       current_idx + len(HEADER_STRING) + FRAME_SIZE_STRING_LEN + str_len]
                    try:
                        # 解码为UTF-8字符串（兼容中文/英文）
                        recv_str = str_bytes.decode('utf-8')
                        print(f"[ESP32字符串消息] {recv_str}")  # 终端打印
                    except UnicodeDecodeError:
                        # 解码失败时替换乱码
                        recv_str = str_bytes.decode('utf-8', errors='replace')
                        print(f"[ESP32字符串消息（解码失败）] {recv_str}")

                    # 移除已处理的字符串帧数据
                    buffer = buffer[current_idx + len(HEADER_STRING) + FRAME_SIZE_STRING_LEN + str_len:]
                else:
                    # 字符串数据不足，等待下一次更新
                    break
            else:
                # 长度字段不足，等待下一次更新
                break

    return [im]


# -------------------------- 启动动画 --------------------------
if __name__ == "__main__":
    print("开始接收数据...")
    ani = FuncAnimation(fig, update, interval=50, blit=False)
    plt.show()
    # 关闭串口
    ser.close()
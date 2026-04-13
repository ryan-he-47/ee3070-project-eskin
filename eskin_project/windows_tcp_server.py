import socket
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import time
from datetime import datetime

# ===== 配置 =====
HOST = '0.0.0.0'
PORT = 8888
# ================

class ESP32Monitor:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32 WiFi 双向通信监控")
        self.root.geometry("900x650")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(True, True)

        self.server_socket = None
        self.client_conn = None
        self.client_addr = None
        self.server_running = False
        self.msg_count_recv = 0
        self.msg_count_send = 0

        self._build_ui()
        self._start_server()

    # ──────────────────────────────────────────
    #  UI 构建
    # ──────────────────────────────────────────
    def _build_ui(self):
        BG       = "#1e1e2e"
        CARD     = "#2a2a3e"
        ACCENT   = "#7c3aed"
        GREEN    = "#22c55e"
        RED      = "#ef4444"
        YELLOW   = "#f59e0b"
        FG       = "#e2e8f0"
        FG_DIM   = "#94a3b8"
        FONT     = ("Consolas", 10)
        FONT_B   = ("Consolas", 10, "bold")

        # ── 顶部标题栏 ──
        header = tk.Frame(self.root, bg=ACCENT, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="  ESP32  WiFi 双向通信监控面板",
                 bg=ACCENT, fg="white", font=("Consolas", 13, "bold")).pack(side=tk.LEFT, padx=12)

        # ── 状态栏（三个指示灯）──
        status_bar = tk.Frame(self.root, bg=CARD, height=44)
        status_bar.pack(fill=tk.X, padx=8, pady=(6, 0))
        status_bar.pack_propagate(False)

        # 服务器状态
        tk.Label(status_bar, text="服务器:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(12,2))
        self.lbl_server = tk.Label(status_bar, text="● 启动中", bg=CARD, fg=YELLOW, font=FONT_B)
        self.lbl_server.pack(side=tk.LEFT, padx=(0,18))

        # ESP32 连接状态
        tk.Label(status_bar, text="ESP32:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0,2))
        self.lbl_esp = tk.Label(status_bar, text="● 未连接", bg=CARD, fg=RED, font=FONT_B)
        self.lbl_esp.pack(side=tk.LEFT, padx=(0,18))

        # ESP32 IP
        tk.Label(status_bar, text="ESP32 IP:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0,2))
        self.lbl_esp_ip = tk.Label(status_bar, text="--", bg=CARD, fg=FG, font=FONT_B)
        self.lbl_esp_ip.pack(side=tk.LEFT, padx=(0,18))

        # 本机 IP
        tk.Label(status_bar, text="本机 IP:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0,2))
        local_ip = self._get_local_ip()
        tk.Label(status_bar, text=local_ip, bg=CARD, fg=GREEN, font=FONT_B).pack(side=tk.LEFT)

        # 端口
        tk.Label(status_bar, text=f"  端口: {PORT}", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=12)

        # ── 统计数字 ──
        stats_frame = tk.Frame(self.root, bg=BG)
        stats_frame.pack(fill=tk.X, padx=8, pady=4)

        for col, (label, color, attr) in enumerate([
            ("收到消息数", GREEN,  "lbl_recv_count"),
            ("发送消息数", ACCENT, "lbl_send_count"),
        ]):
            card = tk.Frame(stats_frame, bg=CARD, relief=tk.FLAT, bd=0)
            card.grid(row=0, column=col, padx=4, pady=2, sticky="ew")
            stats_frame.columnconfigure(col, weight=1)
            tk.Label(card, text=label, bg=CARD, fg=FG_DIM, font=("Consolas", 9)).pack(pady=(6,0))
            lbl = tk.Label(card, text="0", bg=CARD, fg=color, font=("Consolas", 22, "bold"))
            lbl.pack(pady=(0,6))
            setattr(self, attr, lbl)

        # ── 主区域（日志 + 输入） ──
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        # 日志面板
        log_frame = tk.Frame(main, bg=CARD)
        log_frame.grid(row=0, column=0, sticky="nsew", pady=(0,4))

        log_title_bar = tk.Frame(log_frame, bg="#313150", height=28)
        log_title_bar.pack(fill=tk.X)
        log_title_bar.pack_propagate(False)
        tk.Label(log_title_bar, text=" 通信日志", bg="#313150", fg=FG, font=FONT_B).pack(side=tk.LEFT, padx=8)

        btn_clear = tk.Button(log_title_bar, text="清空", bg=ACCENT, fg="white",
                              font=("Consolas", 9), bd=0, padx=8, pady=1,
                              cursor="hand2", command=self._clear_log)
        btn_clear.pack(side=tk.RIGHT, padx=6, pady=3)

        self.log_area = scrolledtext.ScrolledText(
            log_frame, bg="#0f0f1a", fg=FG, font=("Consolas", 10),
            insertbackground="white", wrap=tk.WORD, state=tk.DISABLED,
            relief=tk.FLAT, bd=0, padx=8, pady=6
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 配置日志颜色标签
        self.log_area.tag_config("recv",  foreground="#22c55e")  # 绿 = 收到
        self.log_area.tag_config("send",  foreground="#60a5fa")  # 蓝 = 发出
        self.log_area.tag_config("sys",   foreground="#f59e0b")  # 黄 = 系统
        self.log_area.tag_config("err",   foreground="#ef4444")  # 红 = 错误
        self.log_area.tag_config("time",  foreground="#475569")  # 灰 = 时间戳

        # ── 发送区域 ──
        send_frame = tk.Frame(main, bg=CARD)
        send_frame.grid(row=1, column=0, sticky="ew")

        tk.Label(send_frame, text=" 发送指令:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(8,4))

        self.send_entry = tk.Entry(
            send_frame, bg="#0f0f1a", fg="white", font=("Consolas", 11),
            insertbackground="white", relief=tk.FLAT, bd=4
        )
        self.send_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=6)
        self.send_entry.bind("<Return>", lambda e: self._send_message())

        self.btn_send = tk.Button(
            send_frame, text="发 送", bg=ACCENT, fg="white",
            font=FONT_B, bd=0, padx=16, pady=4, cursor="hand2",
            command=self._send_message
        )
        self.btn_send.pack(side=tk.LEFT, padx=(0,4))

        # ── 快捷指令按钮 ──
        quick_frame = tk.Frame(self.root, bg=BG)
        quick_frame.pack(fill=tk.X, padx=8, pady=(0,8))

        tk.Label(quick_frame, text="快捷指令:", bg=BG, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(4,8))

        cmds = [
            ("LED 开",   "LED_ON",   "#16a34a"),
            ("LED 关",   "LED_OFF",  "#dc2626"),
            ("查询状态", "STATUS",   "#2563eb"),
            ("重启ESP32","RESTART",  "#d97706"),
        ]
        for label, cmd, color in cmds:
            tk.Button(
                quick_frame, text=label, bg=color, fg="white",
                font=FONT_B, bd=0, padx=12, pady=4, cursor="hand2",
                command=lambda c=cmd: self._quick_send(c)
            ).pack(side=tk.LEFT, padx=3)

    # ──────────────────────────────────────────
    #  日志写入（线程安全）
    # ──────────────────────────────────────────
    def _log(self, msg, tag="sys"):
        def _do():
            self.log_area.config(state=tk.NORMAL)
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_area.insert(tk.END, f"[{ts}] ", "time")
            self.log_area.insert(tk.END, msg + "\n", tag)
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _clear_log(self):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete("1.0", tk.END)
        self.log_area.config(state=tk.DISABLED)

    # ──────────────────────────────────────────
    #  状态更新（线程安全）
    # ──────────────────────────────────────────
    def _set_esp_connected(self, addr):
        def _do():
            ip = addr[0] if addr else "--"
            self.lbl_esp.config(text="● 已连接", fg="#22c55e")
            self.lbl_esp_ip.config(text=ip)
        self.root.after(0, _do)

    def _set_esp_disconnected(self):
        def _do():
            self.lbl_esp.config(text="● 未连接", fg="#ef4444")
            self.lbl_esp_ip.config(text="--")
        self.root.after(0, _do)

    def _inc_recv(self):
        self.msg_count_recv += 1
        count = self.msg_count_recv
        self.root.after(0, lambda: self.lbl_recv_count.config(text=str(count)))

    def _inc_send(self):
        self.msg_count_send += 1
        count = self.msg_count_send
        self.root.after(0, lambda: self.lbl_send_count.config(text=str(count)))

    # ──────────────────────────────────────────
    #  获取本机 IP
    # ──────────────────────────────────────────
    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())

    # ──────────────────────────────────────────
    #  TCP Server 启动
    # ──────────────────────────────────────────
    def _start_server(self):
        def _run():
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((HOST, PORT))
            self.server_socket.listen(1)
            self.server_running = True

            def _update():
                self.lbl_server.config(text=f"● 监听中 :{PORT}", fg="#22c55e")
            self.root.after(0, _update)

            local_ip = self._get_local_ip()
            self._log(f"服务器已启动  本机IP: {local_ip}  端口: {PORT}", "sys")
            self._log(f"请将 ESP32 代码中 SERVER_IP 设为: {local_ip}", "sys")
            self._log("等待 ESP32 连接...", "sys")

            while self.server_running:
                try:
                    self.server_socket.settimeout(1.0)
                    conn, addr = self.server_socket.accept()
                    self.client_conn = conn
                    self.client_addr = addr
                    self._set_esp_connected(addr)
                    self._log(f"ESP32 已连接！地址: {addr[0]}:{addr[1]}", "sys")
                    threading.Thread(target=self._receive_loop, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except OSError:
                    break

        threading.Thread(target=_run, daemon=True).start()

    # ──────────────────────────────────────────
    #  接收循环
    # ──────────────────────────────────────────
    def _receive_loop(self, conn, addr):
        buf = ""
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._log(f"[ESP32 → PC]  {line}", "recv")
                        self._inc_recv()
            except Exception:
                break

        conn.close()
        if self.client_conn is conn:
            self.client_conn = None
        self._set_esp_disconnected()
        self._log(f"ESP32 {addr[0]} 已断开连接", "err")

    # ──────────────────────────────────────────
    #  发送消息
    # ──────────────────────────────────────────
    def _send_message(self):
        msg = self.send_entry.get().strip()
        if not msg:
            return
        self._do_send(msg)
        self.send_entry.delete(0, tk.END)

    def _quick_send(self, cmd):
        self._do_send(cmd)

    def _do_send(self, msg):
        if not self.client_conn:
            self._log("发送失败：ESP32 尚未连接", "err")
            return
        try:
            self.client_conn.sendall((msg + "\n").encode("utf-8"))
            self._log(f"[PC → ESP32]  {msg}", "send")
            self._inc_send()
        except Exception as e:
            self._log(f"发送失败: {e}", "err")

    # ──────────────────────────────────────────
    #  关闭
    # ──────────────────────────────────────────
    def on_close(self):
        self.server_running = False
        if self.client_conn:
            try: self.client_conn.close()
            except: pass
        if self.server_socket:
            try: self.server_socket.close()
            except: pass
        self.root.destroy()


# ──────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = ESP32Monitor(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

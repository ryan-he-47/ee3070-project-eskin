import socket
import threading
import tkinter as tk
from tkinter import scrolledtext
import time
from datetime import datetime
import queue
from collections import deque
from pathlib import Path
import sys
import subprocess
import re

import torch
# Set-NetFirewallProfile -Profile Private,Public,Domain -Enabled:False

# 用完立刻打开（写在脚本或提醒里）
# Set-NetFirewallProfile -Profile Private,Public,Domain -Enabled:True
# 
# ===== config =====
HOST = "0.0.0.0"
PORT = 8888

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REWRITE_ROOT = PROJECT_ROOT / "midi_gen_ai_rewrite"
CHECKPOINT = REWRITE_ROOT / "runs" / "event_lm_v2" / "best.pth"

CONTEXT_LEN = 512
TEMPERATURE = 1.15
TOP_K = 12
TOP_P = 0.98

CC_CONTINUATION = 102
CC_START_VALUE = 127
CC_STOP_VALUE = 0
CC_CLEAR_VALUE = 64
# ==================

if str(REWRITE_ROOT) not in sys.path:
    sys.path.insert(0, str(REWRITE_ROOT))

from src.model import EventLSTMLM
from src.tokenizer import EventTokenizer


class RealtimeContinuationEngine:
    def __init__(self, logger):
        self.logger = logger
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.tokenizer = None
        self.model_lock = threading.Lock()

        self.context_tokens = deque(maxlen=CONTEXT_LEN)
        self.last_input_ts = None
        self.last_note_on_ts = None
        self.current_velocity = 64

        self.continuation_active = False
        self.generator_running = False
        self.scheduler_running = False
        self.schedule_queue = queue.PriorityQueue()

        self.generated_time_cursor = 0.0
        self.generation_start_wall = 0.0
        self.active_model_notes = set()

    def load_model(self):
        try:
            ckpt = torch.load(str(CHECKPOINT), map_location=self.device)
            self.tokenizer = EventTokenizer.from_config(ckpt["config"]["tokenizer_config"])
            self.model = EventLSTMLM.from_config(ckpt["config"]["model_config"]).to(self.device)
            self.model.load_state_dict(ckpt["model_state_dict"])
            self.model.eval()

            self.context_tokens.clear()
            self.context_tokens.append(self.tokenizer.bos_id)
            self.logger(f"模型加载成功: {CHECKPOINT}", "sys")
            return True
        except Exception as e:
            self.logger(f"模型加载失败: {e}", "err")
            return False

    def clear_memory(self):
        self.context_tokens.clear()
        if self.tokenizer is not None:
            self.context_tokens.append(self.tokenizer.bos_id)
        self.generated_time_cursor = 0.0
        self.last_input_ts = None
        self.last_note_on_ts = None

    def _sample_from_logits(self, logits: torch.Tensor) -> int:
        probs = torch.softmax(logits / max(TEMPERATURE, 1e-4), dim=-1)

        if TOP_K > 0 and TOP_K < probs.numel():
            top_vals, top_idx = torch.topk(probs, TOP_K)
            filtered = torch.zeros_like(probs)
            filtered[top_idx] = top_vals
            probs = filtered

        if 0.0 < TOP_P < 1.0:
            sorted_probs, sorted_idx = torch.sort(probs, descending=True)
            cumsum = torch.cumsum(sorted_probs, dim=-1)
            keep = cumsum <= TOP_P
            keep[0] = True
            filtered = torch.zeros_like(probs)
            filtered[sorted_idx[keep]] = probs[sorted_idx[keep]]
            probs = filtered

        total = probs.sum()
        if float(total) <= 0.0:
            probs = torch.softmax(logits, dim=-1)
        else:
            probs = probs / total

        return int(torch.multinomial(probs, num_samples=1).item())

    def append_input_midi(self, b0: int, b1: int, b2: int):
        if self.tokenizer is None:
            return

        now = time.monotonic()
        if self.last_input_ts is not None:
            delta = max(0.0, now - self.last_input_ts)
            for t in self.tokenizer.time_to_token_ids(delta):
                self.context_tokens.append(int(t))
        self.last_input_ts = now

        status = b0 & 0xF0
        d1 = b1 & 0x7F
        d2 = b2 & 0x7F

        if status == 0x90 and d2 > 0:
            self.current_velocity = d2
            if self.last_note_on_ts is not None:
                delta = max(0.0, now - self.last_note_on_ts)
                for t in self.tokenizer.time_to_token_ids(delta):
                    self.context_tokens.append(int(t))
            self.last_note_on_ts = now
            self.context_tokens.append(int(self.tokenizer.velocity_to_token_id(d2)))
            if self.tokenizer.low_pitch <= d1 <= self.tokenizer.high_pitch:
                self.context_tokens.append(int(self.tokenizer.pitch_to_token_id(d1)))
        elif status == 0x80 or (status == 0x90 and d2 == 0):
            if self.tokenizer.low_pitch <= d1 <= self.tokenizer.high_pitch:
                self.context_tokens.append(int(self.tokenizer.pitch_off_token_id(d1)))

    def start_continuation(self, send_midi_cb):
        if self.continuation_active:
            return
        self.continuation_active = True
        self.generated_time_cursor = 0.0
        self.generation_start_wall = time.monotonic()
        self.logger("CC102=127: 开始实时续写", "sys")

        if not self.generator_running:
            self.generator_running = True
            threading.Thread(target=self._generator_loop, args=(send_midi_cb,), daemon=True).start()
        if not self.scheduler_running:
            self.scheduler_running = True
            threading.Thread(target=self._scheduler_loop, args=(send_midi_cb,), daemon=True).start()

    def stop_continuation(self, send_midi_cb):
        if not self.continuation_active:
            return
        self.continuation_active = False
        self.logger("CC102=0: 结束实时续写", "sys")

        for pitch in list(self.active_model_notes):
            send_midi_cb(0x80, pitch, 0)
        self.active_model_notes.clear()

    def shutdown(self):
        self.continuation_active = False
        self.generator_running = False
        self.scheduler_running = False

    def _generator_loop(self, send_midi_cb):
        while self.generator_running:
            if not self.continuation_active or self.model is None or self.tokenizer is None:
                time.sleep(0.01)
                continue

            now = time.monotonic()
            ahead = self.generated_time_cursor - (now - self.generation_start_wall)
            if ahead > 0.80:
                time.sleep(0.005)
                continue

            with self.model_lock:
                tokens = list(self.context_tokens)
                if not tokens:
                    tokens = [self.tokenizer.bos_id]
                input_ids = torch.tensor(tokens[-CONTEXT_LEN:], dtype=torch.long, device=self.device).unsqueeze(0)
                with torch.no_grad():
                    logits = self.model(input_ids)[0, -1]
                next_token = self._sample_from_logits(logits)

            self.context_tokens.append(next_token)

            if next_token == self.tokenizer.eos_id:
                continue
            if self.tokenizer.is_time_shift(next_token):
                self.generated_time_cursor += float(self.tokenizer.token_id_to_time_shift(next_token))
                continue
            if self.tokenizer.is_velocity(next_token):
                self.current_velocity = int(self.tokenizer.token_id_to_velocity(next_token))
                continue

            send_at = self.generation_start_wall + self.generated_time_cursor
            if self.tokenizer.is_note_on(next_token):
                pitch = int(self.tokenizer.token_id_to_pitch(next_token))
                self.active_model_notes.add(pitch)
                self.schedule_queue.put((send_at, (0x90, pitch, self.current_velocity)))
            elif self.tokenizer.is_note_off(next_token):
                pitch = int(self.tokenizer.token_id_to_pitch(next_token))
                self.active_model_notes.discard(pitch)
                self.schedule_queue.put((send_at, (0x80, pitch, 0)))

    def _scheduler_loop(self, send_midi_cb):
        while self.scheduler_running:
            if not self.continuation_active:
                time.sleep(0.01)
                continue

            try:
                send_at, frame = self.schedule_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            delay = send_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            send_midi_cb(*frame)


class ESP32Monitor:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32 WiFi 双向通信监控 + 实时续写")
        self.root.geometry("920x680")
        self.root.configure(bg="#1e1e2e")

        self.server_socket = None
        self.client_conn = None
        self.client_addr = None
        self.server_running = False
        self.msg_count_recv = 0
        self.msg_count_send = 0

        self.engine = RealtimeContinuationEngine(self._log)
        self.local_ips = self._get_local_ips()
        self.preferred_ip = self._pick_preferred_ip(self.local_ips)

        self._build_ui()
        self.engine.load_model()
        self._start_server()

    def _build_ui(self):
        BG = "#1e1e2e"
        CARD = "#2a2a3e"
        ACCENT = "#7c3aed"
        GREEN = "#22c55e"
        RED = "#ef4444"
        YELLOW = "#f59e0b"
        FG = "#e2e8f0"
        FG_DIM = "#94a3b8"
        FONT = ("Consolas", 10)
        FONT_B = ("Consolas", 10, "bold")

        header = tk.Frame(self.root, bg=ACCENT, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="  ESP32 WiFi MIDI 实时续写服务", bg=ACCENT, fg="white", font=("Consolas", 13, "bold")).pack(side=tk.LEFT, padx=12)

        status_bar = tk.Frame(self.root, bg=CARD, height=44)
        status_bar.pack(fill=tk.X, padx=8, pady=(6, 0))
        status_bar.pack_propagate(False)

        tk.Label(status_bar, text="服务器:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(12, 2))
        self.lbl_server = tk.Label(status_bar, text="● 启动中", bg=CARD, fg=YELLOW, font=FONT_B)
        self.lbl_server.pack(side=tk.LEFT, padx=(0, 18))

        tk.Label(status_bar, text="ESP32:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0, 2))
        self.lbl_esp = tk.Label(status_bar, text="● 未连接", bg=CARD, fg=RED, font=FONT_B)
        self.lbl_esp.pack(side=tk.LEFT, padx=(0, 18))

        tk.Label(status_bar, text="续写状态:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0, 2))
        self.lbl_mode = tk.Label(status_bar, text="● 空闲", bg=CARD, fg=YELLOW, font=FONT_B)
        self.lbl_mode.pack(side=tk.LEFT, padx=(0, 18))

        tk.Label(status_bar, text="ESP32 IP:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0, 2))
        self.lbl_esp_ip = tk.Label(status_bar, text="--", bg=CARD, fg=FG, font=FONT_B)
        self.lbl_esp_ip.pack(side=tk.LEFT, padx=(0, 18))

        tk.Label(status_bar, text="本机 IP:", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=(0, 2))
        tk.Label(status_bar, text=self.preferred_ip, bg=CARD, fg=GREEN, font=FONT_B).pack(side=tk.LEFT)
        tk.Label(status_bar, text=f"  端口: {PORT}", bg=CARD, fg=FG_DIM, font=FONT).pack(side=tk.LEFT, padx=12)

        stats_frame = tk.Frame(self.root, bg=BG)
        stats_frame.pack(fill=tk.X, padx=8, pady=4)

        for col, (label, color, attr) in enumerate([
            ("收到消息数", GREEN, "lbl_recv_count"),
            ("发送消息数", ACCENT, "lbl_send_count"),
        ]):
            card = tk.Frame(stats_frame, bg=CARD, relief=tk.FLAT, bd=0)
            card.grid(row=0, column=col, padx=4, pady=2, sticky="ew")
            stats_frame.columnconfigure(col, weight=1)
            tk.Label(card, text=label, bg=CARD, fg=FG_DIM, font=("Consolas", 9)).pack(pady=(6, 0))
            lbl = tk.Label(card, text="0", bg=CARD, fg=color, font=("Consolas", 22, "bold"))
            lbl.pack(pady=(0, 6))
            setattr(self, attr, lbl)

        log_frame = tk.Frame(self.root, bg=CARD)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            bg="#0f0f1a",
            fg=FG,
            font=("Consolas", 10),
            insertbackground="white",
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=6,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        self.log_area.tag_config("recv", foreground="#22c55e")
        self.log_area.tag_config("send", foreground="#60a5fa")
        self.log_area.tag_config("sys", foreground="#f59e0b")
        self.log_area.tag_config("err", foreground="#ef4444")
        self.log_area.tag_config("time", foreground="#475569")

    def _log(self, msg, tag="sys"):
        def _do():
            self.log_area.config(state=tk.NORMAL)
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_area.insert(tk.END, f"[{ts}] ", "time")
            self.log_area.insert(tk.END, msg + "\n", tag)
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)

        self.root.after(0, _do)

    def _set_mode(self, active: bool):
        def _do():
            if active:
                self.lbl_mode.config(text="● 续写中", fg="#22c55e")
            else:
                self.lbl_mode.config(text="● 空闲", fg="#f59e0b")

        self.root.after(0, _do)

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
            self.lbl_mode.config(text="● 空闲", fg="#f59e0b")

        self.root.after(0, _do)

    def _inc_recv(self):
        self.msg_count_recv += 1
        count = self.msg_count_recv
        self.root.after(0, lambda: self.lbl_recv_count.config(text=str(count)))

    def _inc_send(self):
        self.msg_count_send += 1
        count = self.msg_count_send
        self.root.after(0, lambda: self.lbl_send_count.config(text=str(count)))

    def _get_local_ips(self):
        ips = set()

        try:
            host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
            for ip in host_ips:
                if ip and not ip.startswith("127."):
                    ips.add(ip)
        except Exception:
            pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                ips.add(ip)
        except Exception:
            pass

        try:
            out = subprocess.check_output(["ipconfig"], text=True, encoding="gbk", errors="ignore")
            for match in re.findall(r"\b([0-9]{1,3}(?:\.[0-9]{1,3}){3})\b", out):
                parts = match.split(".")
                if len(parts) != 4:
                    continue
                try:
                    nums = [int(p) for p in parts]
                except ValueError:
                    continue
                if any(n < 0 or n > 255 for n in nums):
                    continue
                if match.startswith("127.") or match.startswith("255.") or match.startswith("0."):
                    continue
                ips.add(match)
        except Exception:
            pass

        if not ips:
            return ["0.0.0.0"]
        return sorted(ips)

    def _pick_preferred_ip(self, ips):
        for ip in ips:
            if ip.startswith("192.168.137."):
                return ip
        return ips[0] if ips else "0.0.0.0"

    def _send_midi_to_esp32(self, b0: int, b1: int, b2: int):
        if not self.client_conn:
            return
        try:
            line = f"MIDI:{b0 & 0xFF},{b1 & 0x7F},{b2 & 0x7F}"
            self.client_conn.sendall((line + "\n").encode("utf-8"))
            self._inc_send()
        except Exception as e:
            self._log(f"发送MIDI失败: {e}", "err")

    def _start_server(self):
        def _run():
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((HOST, PORT))
            self.server_socket.listen(1)
            self.server_running = True

            self.root.after(0, lambda: self.lbl_server.config(text=f"● 监听中 :{PORT}", fg="#22c55e"))
            self._log(f"服务器已启动 本机IP: {self.preferred_ip} 端口: {PORT}", "sys")
            self._log(f"候选IPv4: {', '.join(self.local_ips)}", "sys")
            self._log(f"请将 ESP32 代码中 SERVER_IP 设为: {self.preferred_ip}", "sys")
            self._log("协议: ESP32->PC MIDI:b0,b1,b2 ; PC->ESP32 MIDI:b0,b1,b2", "sys")

            while self.server_running:
                try:
                    self.server_socket.settimeout(1.0)
                    conn, addr = self.server_socket.accept()
                    self.client_conn = conn
                    self.client_addr = addr
                    self._set_esp_connected(addr)
                    self._log(f"ESP32 已连接: {addr[0]}:{addr[1]}", "sys")
                    threading.Thread(target=self._receive_loop, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except OSError:
                    break

        threading.Thread(target=_run, daemon=True).start()

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
                        self._inc_recv()
                        self._log(f"[ESP32 -> PC] {line}", "recv")
                        self._handle_incoming_line(line)
            except Exception:
                break

        try:
            conn.close()
        except Exception:
            pass
        if self.client_conn is conn:
            self.client_conn = None

        self.engine.stop_continuation(self._send_midi_to_esp32)
        self._set_mode(False)
        self._set_esp_disconnected()
        self._log(f"ESP32 {addr[0]} 已断开连接", "err")

    def _handle_incoming_line(self, line: str):
        if not line.startswith("MIDI:"):
            return

        payload = line[5:]
        parts = payload.split(",")
        if len(parts) != 3:
            return

        try:
            b0 = int(parts[0]) & 0xFF
            b1 = int(parts[1]) & 0x7F
            b2 = int(parts[2]) & 0x7F
        except ValueError:
            return

        status = b0 & 0xF0
        if status == 0xB0 and b1 == CC_CONTINUATION:
            if b2 == CC_START_VALUE:
                self.engine.start_continuation(self._send_midi_to_esp32)
                self._set_mode(True)
            elif b2 == CC_STOP_VALUE:
                self.engine.stop_continuation(self._send_midi_to_esp32)
                self._set_mode(False)
            elif b2 == CC_CLEAR_VALUE:
                self.engine.clear_memory()
                self._log("CC102=64 清空模型记忆", "sys")
            return

        self.engine.append_input_midi(b0, b1, b2)

    def on_close(self):
        self.server_running = False
        self.engine.shutdown()
        if self.client_conn:
            try:
                self.client_conn.close()
            except Exception:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ESP32Monitor(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

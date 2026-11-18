import tkinter as tk
from tkinter import messagebox
import socket
import threading
import json
import queue
import time

GUI_LISTEN_IP = "0.0.0.0"
GUI_LISTEN_PORT = 5005
ESP32_GATEWAY_IP = "127.0.0.1"   # Change to ESP32 gateway IP later
ESP32_COMMAND_PORT = 5006
MAX_TOTAL_MANUAL_OUTPUT = 200.0
NUM_FANS = 4


class SmartFanGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Fan Control System")
        self.root.geometry("1150x760")
        self.root.minsize(950, 650)

        # ---------------- TEMP SYSTEM VARIABLES ----------------
        self.system_mode = "AUTO"
        self.person_detected = False
        self.detected_quadrant = "--"
        self.total_fan_output = 0.0
        self.mesh_health = "UNKNOWN"
        self.last_update_time = None

        # ---------------- TEMP FAN VARIABLES ----------------
        self.fans = {
            i: {
                "online": False,
                "fan_on": False,
                "speed_percent": 0.0,
                "distance_m": None,
                "person_detected": False,
                "rpm": None,
            }
            for i in range(1, NUM_FANS + 1)
        }

        self.manual_speed_vars = {
            i: tk.StringVar(value="0") for i in range(1, NUM_FANS + 1)
        }
        self.manual_on_vars = {
            i: tk.BooleanVar(value=False) for i in range(1, NUM_FANS + 1)
        }
        self.mode_var = tk.StringVar(value="AUTO")

        self.rx_queue = queue.Queue()
        self.build_gui()
        self.start_udp_listener()
        self.root.after(50, self.process_network_messages)
        self.root.after(500, self.check_connection_timeout)
        self.log_event("GUI started. Waiting for fan data...")

    def build_gui(self):
        tk.Label(
            self.root,
            text="SMART FAN CONTROL SYSTEM",
            font=("Arial", 22, "bold")
        ).pack(pady=(15, 5))

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=20, pady=5)

        self.person_label = tk.Label(top_frame, text="Person: UNDETECTED", font=("Arial", 12, "bold"))
        self.person_label.pack(side="left", padx=15)
        self.mesh_label = tk.Label(top_frame, text="Mesh: UNKNOWN", font=("Arial", 12, "bold"))
        self.mesh_label.pack(side="left", padx=15)
        self.quadrant_label = tk.Label(top_frame, text="Detected Quadrant: --", font=("Arial", 12, "bold"))
        self.quadrant_label.pack(side="left", padx=15)
        self.total_label = tk.Label(top_frame, text="Total Fan Output: 0%", font=("Arial", 12, "bold"))
        self.total_label.pack(side="left", padx=15)

        mode_frame = tk.LabelFrame(self.root, text="Operating Mode", font=("Arial", 11, "bold"))
        mode_frame.pack(fill="x", padx=20, pady=8)

        tk.Radiobutton(
            mode_frame, text="AUTO", variable=self.mode_var, value="AUTO",
            command=self.on_mode_changed, font=("Arial", 11, "bold")
        ).pack(side="left", padx=20, pady=8)

        tk.Radiobutton(
            mode_frame, text="MANUAL", variable=self.mode_var, value="MANUAL",
            command=self.on_mode_changed, font=("Arial", 11, "bold")
        ).pack(side="left", padx=20, pady=8)

        self.mode_warning = tk.Label(mode_frame, text="Automatic fan control active", font=("Arial", 10))
        self.mode_warning.pack(side="left", padx=20)

        fan_grid = tk.Frame(self.root)
        fan_grid.pack(fill="both", expand=True, padx=20, pady=5)
        fan_grid.grid_columnconfigure(0, weight=1)
        fan_grid.grid_columnconfigure(1, weight=1)
        fan_grid.grid_rowconfigure(0, weight=1)
        fan_grid.grid_rowconfigure(1, weight=1)

        self.fan_widgets = {}
        positions = {1: (0, 0), 2: (0, 1), 3: (1, 0), 4: (1, 1)}
        for fan_id, (row, col) in positions.items():
            self.create_fan_card(fan_grid, fan_id, row, col)

        log_frame = tk.LabelFrame(self.root, text="System Log", font=("Arial", 11, "bold"))
        log_frame.pack(fill="both", padx=20, pady=(5, 15))
        self.log_box = tk.Text(log_frame, height=7, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)

        self.update_manual_control_states()

    def create_fan_card(self, parent, fan_id, row, col):
        card = tk.LabelFrame(parent, text=f"Fan {fan_id}", font=("Arial", 14, "bold"), padx=12, pady=10)
        card.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)

        labels = {}
        labels["status"] = tk.Label(card, text="Status: OFF", font=("Arial", 11))
        labels["speed"] = tk.Label(card, text="Speed: 0%", font=("Arial", 11))
        labels["distance"] = tk.Label(card, text="Distance: -- m", font=("Arial", 11))
        labels["detection"] = tk.Label(card, text="Person: NOT DETECTED", font=("Arial", 11))
        labels["mesh"] = tk.Label(card, text="Mesh Status: OFFLINE", font=("Arial", 11))
        labels["rpm"] = tk.Label(card, text="RPM: --", font=("Arial", 11))

        for r, key in enumerate(["status", "speed", "distance", "detection", "mesh", "rpm"]):
            labels[key].grid(row=r, column=0, sticky="w", pady=2)

        tk.Frame(card, height=2, bd=1, relief="sunken").grid(row=6, column=0, columnspan=3, sticky="ew", pady=8)
        tk.Label(card, text="Manual Speed (0-100%):", font=("Arial", 10)).grid(row=7, column=0, sticky="w")

        speed_entry = tk.Entry(card, textvariable=self.manual_speed_vars[fan_id], width=8)
        speed_entry.grid(row=7, column=1, padx=5)

        onoff_button = tk.Button(card, text="Turn ON", width=12, command=lambda i=fan_id: self.toggle_manual_fan(i))
        onoff_button.grid(row=8, column=0, pady=6, sticky="w")

        apply_button = tk.Button(card, text="Apply Speed", width=12, command=lambda i=fan_id: self.apply_manual_speed(i))
        apply_button.grid(row=8, column=1, pady=6, padx=5)

        labels.update({
            "speed_entry": speed_entry,
            "onoff_button": onoff_button,
            "apply_button": apply_button,
        })
        self.fan_widgets[fan_id] = labels

    def start_udp_listener(self):
        def listener():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((GUI_LISTEN_IP, GUI_LISTEN_PORT))
            sock.settimeout(1.0)
            while True:
                try:
                    data, _ = sock.recvfrom(8192)
                    self.rx_queue.put(("DATA", json.loads(data.decode("utf-8"))))
                except socket.timeout:
                    pass
                except Exception as e:
                    self.rx_queue.put(("ERROR", str(e)))

        threading.Thread(target=listener, daemon=True).start()

    def process_network_messages(self):
        while not self.rx_queue.empty():
            msg_type, data = self.rx_queue.get_nowait()
            if msg_type == "DATA":
                self.handle_status_packet(data)
            else:
                self.log_event(f"Network error: {data}")
        self.root.after(50, self.process_network_messages)

    def handle_status_packet(self, packet):
        if packet.get("type") != "status":
            return

        self.last_update_time = time.time()
        self.person_detected = bool(packet.get("person_detected", False))
        self.detected_quadrant = packet.get("detected_quadrant", "--")
        self.mesh_health = packet.get("mesh_health", "UNKNOWN")

        incoming_fans = packet.get("fans", {})
        for fan_id in range(1, NUM_FANS + 1):
            src = incoming_fans.get(str(fan_id), {})
            fan = self.fans[fan_id]
            fan["online"] = bool(src.get("online", False))
            fan["fan_on"] = bool(src.get("fan_on", False))
            fan["speed_percent"] = float(src.get("speed_percent", 0.0))
            fan["distance_m"] = src.get("distance_m")
            fan["person_detected"] = bool(src.get("person_detected", False))
            fan["rpm"] = src.get("rpm")

        self.total_fan_output = sum(
            fan["speed_percent"] for fan in self.fans.values() if fan["fan_on"]
        )
        self.refresh_display()

    def refresh_display(self):
        self.person_label.config(text=f"Person: {'DETECTED' if self.person_detected else 'UNDETECTED'}")
        self.mesh_label.config(text=f"Mesh: {self.mesh_health}")
        self.quadrant_label.config(text=f"Detected Quadrant: {self.detected_quadrant}")
        self.total_label.config(text=f"Total Fan Output: {self.total_fan_output:.0f}%")

        for fan_id, fan in self.fans.items():
            w = self.fan_widgets[fan_id]
            w["status"].config(text=f"Status: {'ON' if fan['fan_on'] else 'OFF'}")
            w["speed"].config(text=f"Speed: {fan['speed_percent']:.0f}%")
            w["distance"].config(text="Distance: -- m" if fan["distance_m"] is None else f"Distance: {float(fan['distance_m']):.2f} m")
            w["detection"].config(text=f"Person: {'DETECTED' if fan['person_detected'] else 'NOT DETECTED'}")
            w["mesh"].config(text=f"Mesh Status: {'ONLINE' if fan['online'] else 'OFFLINE'}")
            w["rpm"].config(text=f"RPM: {fan['rpm'] if fan['rpm'] is not None else '--'}")

        self.update_manual_control_states()

    def on_mode_changed(self):
        self.system_mode = self.mode_var.get()
        if self.system_mode == "AUTO":
            self.mode_warning.config(text="Automatic fan control active")
        else:
            self.mode_warning.config(text="MANUAL MODE - automatic fan control disabled")

        self.log_event(f"{self.system_mode} mode selected")
        self.send_command({"type": "command", "command": "set_mode", "mode": self.system_mode})
        self.update_manual_control_states()

    def update_manual_control_states(self):
        manual_mode = self.mode_var.get() == "MANUAL"
        for fan_id in range(1, NUM_FANS + 1):
            enabled = manual_mode and self.fans[fan_id]["online"]
            state = "normal" if enabled else "disabled"
            self.fan_widgets[fan_id]["speed_entry"].config(state=state)
            self.fan_widgets[fan_id]["onoff_button"].config(state=state)
            self.fan_widgets[fan_id]["apply_button"].config(state=state)

    def validate_speed(self, fan_id):
        try:
            speed = float(self.manual_speed_vars[fan_id].get())
        except ValueError:
            messagebox.showerror("Invalid Speed", f"Fan {fan_id}: Enter a number between 0 and 100.")
            return None
        if not 0 <= speed <= 100:
            messagebox.showerror("Invalid Speed", f"Fan {fan_id}: Speed must be between 0% and 100%.")
            return None
        return speed

    def requested_manual_total(self, override_fan=None, override_speed=None, override_on=None):
        total = 0.0
        for fan_id in range(1, NUM_FANS + 1):
            is_on = self.manual_on_vars[fan_id].get()
            if fan_id == override_fan and override_on is not None:
                is_on = override_on
            if not is_on:
                continue
            try:
                speed = float(self.manual_speed_vars[fan_id].get())
            except ValueError:
                speed = 0.0
            if fan_id == override_fan and override_speed is not None:
                speed = override_speed
            total += speed
        return total

    def apply_manual_speed(self, fan_id):
        if self.mode_var.get() != "MANUAL":
            return
        speed = self.validate_speed(fan_id)
        if speed is None:
            return

        total = self.requested_manual_total(override_fan=fan_id, override_speed=speed)
        if total > MAX_TOTAL_MANUAL_OUTPUT:
            messagebox.showwarning("Total Output Limit", f"Command not sent.\nRequested total = {total:.1f}%\nMaximum = {MAX_TOTAL_MANUAL_OUTPUT:.0f}%")
            return

        self.send_command({"type": "command", "command": "set_fan_speed", "fan_id": fan_id, "speed_percent": speed})
        self.log_event(f"Manual command: Fan {fan_id} speed -> {speed:.0f}%")

    def toggle_manual_fan(self, fan_id):
        if self.mode_var.get() != "MANUAL":
            return

        new_state = not self.manual_on_vars[fan_id].get()
        speed = self.validate_speed(fan_id) if new_state else 0.0
        if new_state and speed is None:
            return

        total = self.requested_manual_total(
            override_fan=fan_id,
            override_speed=speed if new_state else None,
            override_on=new_state,
        )
        if total > MAX_TOTAL_MANUAL_OUTPUT:
            messagebox.showwarning("Total Output Limit", f"Cannot turn Fan {fan_id} ON.\nRequested total = {total:.1f}%\nMaximum = {MAX_TOTAL_MANUAL_OUTPUT:.0f}%")
            return

        self.manual_on_vars[fan_id].set(new_state)
        self.fan_widgets[fan_id]["onoff_button"].config(text="Turn OFF" if new_state else "Turn ON")
        self.send_command({"type": "command", "command": "set_fan_power", "fan_id": fan_id, "fan_on": new_state})
        self.log_event(f"Manual command: Fan {fan_id} -> {'ON' if new_state else 'OFF'}")

    def send_command(self, command):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(json.dumps(command).encode("utf-8"), (ESP32_GATEWAY_IP, ESP32_COMMAND_PORT))
            sock.close()
        except Exception as e:
            self.log_event(f"Failed to send command: {e}")

    def check_connection_timeout(self):
        if self.last_update_time is not None and time.time() - self.last_update_time > 3.0:
            self.mesh_health = "NO DATA"
            self.mesh_label.config(text="Mesh: NO DATA")
            for fan_id in range(1, NUM_FANS + 1):
                self.fans[fan_id]["online"] = False
            self.update_manual_control_states()
        self.root.after(500, self.check_connection_timeout)

    def log_event(self, text):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"{timestamp}  {text}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    SmartFanGUI(root)
    root.mainloop()

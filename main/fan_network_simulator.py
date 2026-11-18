import socket
import json
import time
import math
import random
import threading

GUI_IP = "127.0.0.1"
GUI_PORT = 5005
SIMULATOR_LISTEN_IP = "0.0.0.0"
SIMULATOR_COMMAND_PORT = 5006
UPDATE_INTERVAL = 0.20  # 5 updates/second
MAX_TOTAL_AUTO_OUTPUT = 200.0
NUM_FANS = 4
ROOM_WIDTH = 6.0
ROOM_HEIGHT = 6.0

FAN_POSITIONS = {
    1: (0.0, 0.0),
    2: (ROOM_WIDTH, 0.0),
    3: (0.0, ROOM_HEIGHT),
    4: (ROOM_WIDTH, ROOM_HEIGHT),
}

system_mode = "AUTO"

fans = {
    i: {
        "online": True,
        "fan_on": True,
        "speed_percent": 50.0,
        "distance_m": None,
        "person_detected": False,
        "rpm": 1000,
    }
    for i in range(1, NUM_FANS + 1)
}

manual_speeds = {1: 50.0, 2: 50.0, 3: 50.0, 4: 50.0}
manual_power = {1: True, 2: True, 3: True, 4: True}


def clamp(value, low, high):
    return max(low, min(high, value))


def fake_person_position(t):
    """Move a fake person smoothly around the room."""
    center_x = ROOM_WIDTH / 2
    center_y = ROOM_HEIGHT / 2
    radius_x = ROOM_WIDTH * 0.35
    radius_y = ROOM_HEIGHT * 0.35

    x = center_x + radius_x * math.sin(t * 0.35)
    y = center_y + radius_y * math.sin(t * 0.53 + 1.2)
    return x, y


def get_quadrant(x, y):
    if x < ROOM_WIDTH / 2 and y < ROOM_HEIGHT / 2:
        return "Q1"
    if x >= ROOM_WIDTH / 2 and y < ROOM_HEIGHT / 2:
        return "Q2"
    if x < ROOM_WIDTH / 2 and y >= ROOM_HEIGHT / 2:
        return "Q3"
    return "Q4"


def calculate_distances(person_x, person_y):
    distances = {}
    for fan_id, (fan_x, fan_y) in FAN_POSITIONS.items():
        dx = person_x - fan_x
        dy = person_y - fan_y
        distance = math.sqrt(dx * dx + dy * dy)

        # Small fake sensor noise
        distance += random.uniform(-0.04, 0.04)
        distances[fan_id] = max(0.10, distance)
    return distances


def calculate_auto_speeds(distances):
    """
    Inverse-square weighting:
        score = 1 / distance^2

    Fan speeds are normalized to total 200%.
    Each fan is capped at 100%, then excess is redistributed.
    """
    scores = {
        fan_id: 1.0 / max(distance, 0.15) ** 2
        for fan_id, distance in distances.items()
    }

    result = {fan_id: 0.0 for fan_id in distances}
    remaining_ids = set(distances.keys())
    remaining_total = MAX_TOTAL_AUTO_OUTPUT

    while remaining_ids:
        remaining_score = sum(scores[i] for i in remaining_ids)
        if remaining_score <= 0:
            equal_share = remaining_total / len(remaining_ids)
            for i in remaining_ids:
                result[i] = min(100.0, equal_share)
            break

        capped_any = False
        for i in list(remaining_ids):
            share = remaining_total * scores[i] / remaining_score
            if share >= 100.0:
                result[i] = 100.0
                remaining_total -= 100.0
                remaining_ids.remove(i)
                capped_any = True

        if not capped_any:
            for i in remaining_ids:
                result[i] = remaining_total * scores[i] / remaining_score
            break

    return result


def update_simulated_fans():
    t = time.time()
    person_x, person_y = fake_person_position(t)
    distances = calculate_distances(person_x, person_y)
    quadrant = get_quadrant(person_x, person_y)

    if system_mode == "AUTO":
        speeds = calculate_auto_speeds(distances)
        for fan_id in range(1, NUM_FANS + 1):
            fans[fan_id]["distance_m"] = round(distances[fan_id], 2)
            fans[fan_id]["person_detected"] = quadrant == f"Q{fan_id}"
            fans[fan_id]["speed_percent"] = round(speeds[fan_id], 1)
            fans[fan_id]["fan_on"] = speeds[fan_id] > 0.1
            fans[fan_id]["rpm"] = int(300 + 17 * speeds[fan_id]) if fans[fan_id]["fan_on"] else 0
    else:
        # Sensors still update in MANUAL mode, but fan outputs come from GUI commands.
        for fan_id in range(1, NUM_FANS + 1):
            fans[fan_id]["distance_m"] = round(distances[fan_id], 2)
            fans[fan_id]["person_detected"] = quadrant == f"Q{fan_id}"
            fans[fan_id]["fan_on"] = manual_power[fan_id]
            if manual_power[fan_id]:
                fans[fan_id]["speed_percent"] = manual_speeds[fan_id]
                fans[fan_id]["rpm"] = int(300 + 17 * manual_speeds[fan_id])
            else:
                fans[fan_id]["speed_percent"] = 0.0
                fans[fan_id]["rpm"] = 0

    return quadrant


def make_status_packet(quadrant):
    mesh_healthy = all(f["online"] for f in fans.values())
    packet = {
        "type": "status",
        "person_detected": True,
        "detected_quadrant": quadrant,
        "mesh_health": "HEALTHY" if mesh_healthy else "DEGRADED",
        "fans": {}
    }

    for fan_id, fan in fans.items():
        packet["fans"][str(fan_id)] = {
            "online": fan["online"],
            "fan_on": fan["fan_on"],
            "speed_percent": fan["speed_percent"],
            "distance_m": fan["distance_m"],
            "person_detected": fan["person_detected"],
            "rpm": fan["rpm"],
        }
    return packet


def status_sender_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        quadrant = update_simulated_fans()
        packet = make_status_packet(quadrant)
        sock.sendto(json.dumps(packet).encode("utf-8"), (GUI_IP, GUI_PORT))
        time.sleep(UPDATE_INTERVAL)


def command_listener_loop():
    global system_mode

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SIMULATOR_LISTEN_IP, SIMULATOR_COMMAND_PORT))
    print(f"Listening for GUI commands on UDP {SIMULATOR_COMMAND_PORT}...")

    while True:
        data, _ = sock.recvfrom(4096)
        try:
            command = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            continue

        if command.get("type") != "command":
            continue

        action = command.get("command")

        if action == "set_mode":
            requested_mode = command.get("mode", "AUTO").upper()
            if requested_mode in ("AUTO", "MANUAL"):
                system_mode = requested_mode
                print(f"[COMMAND] Mode -> {system_mode}")

        elif action == "set_fan_speed":
            fan_id = int(command.get("fan_id", 0))
            speed = float(command.get("speed_percent", 0))
            if fan_id in manual_speeds:
                manual_speeds[fan_id] = clamp(speed, 0.0, 100.0)
                print(f"[COMMAND] Fan {fan_id} manual speed -> {manual_speeds[fan_id]:.0f}%")

        elif action == "set_fan_power":
            fan_id = int(command.get("fan_id", 0))
            fan_on = bool(command.get("fan_on", False))
            if fan_id in manual_power:
                manual_power[fan_id] = fan_on
                print(f"[COMMAND] Fan {fan_id} -> {'ON' if fan_on else 'OFF'}")


if __name__ == "__main__":
    print("===========================================")
    print(" Smart Fan ESP32 Test Simulator")
    print("===========================================")
    print("Sending status packets to GUI on UDP 5005")
    print("The fake person moves continuously around a 6 m x 6 m room.")
    print("Switch the GUI to MANUAL to test manual fan commands.")
    print("Press Ctrl+C here to stop the simulator.\n")

    threading.Thread(target=command_listener_loop, daemon=True).start()

    try:
        status_sender_loop()
    except KeyboardInterrupt:
        print("\nSimulator stopped.")

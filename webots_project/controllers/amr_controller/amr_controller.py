from __future__ import annotations
import json
import math
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from controller import Robot


import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


MQTT_ENABLED        = os.environ.get("AMR_MQTT", "1") == "1"
MQTT_BROKER         = os.environ.get("AMR_MQTT_BROKER", "localhost")
MQTT_PORT           = int(os.environ.get("AMR_MQTT_PORT", "1883"))
TELEMETRY_INTERVAL  = 1.0
COMMAND_POLL        = 0.25
MAX_SPEED           = 12.0
CRUISE_SPEED        = 8.0
WP_TOLERANCE        = 0.35
DOCK_TOLERANCE      = 0.12
WHEEL_R             = 0.06
TRACK_W             = 0.28
LOW_SOC_PCT         = 18.0
FULL_SOC_PCT        = 95.0
STUCK_DIST          = 0.08
STUCK_TIME          = 2.5
RECOVERY_TIME       = 1.5
MAX_RECOVERIES      = 4
SENSOR_WARMUP       = 0.5
OBSTACLE_CLOSE_M    = 0.35
OBSTACLE_SLOW_M     = 0.80


NODES: Dict[str, Tuple[float, float]] = {

    "PICKUP_RAW":    (5.0,   4.5),

    "C_S":           (11.5,  4.5),
    "C_MID_S":       (11.5,  10.0),
    "C_MID_N":       (11.5,  11.0),
    "C_N":           (11.5,  17.5),

    "C_MID_A":       (18.0,  10.0),
    "C_MID_W":       (27.5,  10.0),
    "C_MID_F":       (34.0,  10.0),


    "DROPOFF_A":     (18.0,   9.0),
    "DROPOFF_B":     (18.0,  11.0),
    "DROPOFF_W":     (27.5,   9.0),
    "DROPOFF_PKG":   (27.5,  14.0),
    "DROPOFF_FIN_A": (34.0,   6.0),
    "DROPOFF_FIN_B": (34.0,  16.0),

    "C_MID_W1":      (5.0,   10.0),
    "PICKUP_QC":     (5.0,   18.0),
    "DOCK_CS01":     (2.0,   13.0),
    "DOCK_CS02":     (5.0,   13.0),
    "DOCK_CS03":     (8.0,   13.0),
}


NEIGHBOURS: Dict[str, List[str]] = {
    "PICKUP_RAW":    ["C_S"],
    "C_S":           ["PICKUP_RAW", "C_MID_S", "DROPOFF_A"],
    "C_MID_S":       ["C_S", "C_MID_N", "C_MID_W1", "C_MID_A"],
    "C_MID_N":       ["C_MID_S", "C_N", "DROPOFF_B"],
    "C_N":           ["C_MID_N"],
    "C_MID_A":       ["C_MID_S", "C_MID_W", "DROPOFF_A", "DROPOFF_B"],
    "C_MID_W":       ["C_MID_A", "C_MID_F", "DROPOFF_W", "DROPOFF_PKG"],
    "C_MID_F":       ["C_MID_W", "DROPOFF_FIN_A", "DROPOFF_FIN_B"],
    "DROPOFF_A":     ["C_S", "C_MID_A"],
    "DROPOFF_B":     ["C_MID_N", "C_MID_A"],
    "DROPOFF_W":     ["C_MID_W"],
    "DROPOFF_PKG":   ["C_MID_W"],
    "DROPOFF_FIN_A": ["C_MID_F"],
    "DROPOFF_FIN_B": ["C_MID_F"],
    "C_MID_W1":      ["C_MID_S", "PICKUP_QC", "DOCK_CS01", "DOCK_CS02", "DOCK_CS03"],
    "PICKUP_QC":     ["C_MID_W1"],
    "DOCK_CS01":     ["C_MID_W1"],
    "DOCK_CS02":     ["C_MID_W1"],
    "DOCK_CS03":     ["C_MID_W1"],
}


MISSIONS: Dict[str, List[Tuple[str, str, float, str]]] = {
    "amr_01": [
        ("PICKUP_RAW",   "load",    3.0, "Завантаження сировини на складі"),
        ("DROPOFF_A",    "unload",  3.0, "Розвантаження на Ділянку збирання A"),
        ("PICKUP_RAW",   "load",    3.0, "Завантаження партії для Збирання B"),
        ("DROPOFF_B",    "unload",  3.0, "Розвантаження на Ділянку збирання B"),
    ],
    "amr_02": [
        ("DROPOFF_A",    "load",    2.5, "Забір зібраного вузла зі столу A"),
        ("DROPOFF_W",    "unload",  2.5, "Передача на зварювальний пост"),
        ("DROPOFF_W",    "inspect", 4.0, "Очікування завершення зварювання"),
        ("DROPOFF_W",    "load",    2.0, "Забір звареного виробу"),
        ("DROPOFF_PKG",  "unload",  2.0, "Передача на пакувальний конвеєр"),
        ("DROPOFF_FIN_A","unload",  2.0, "Переміщення на склад готової продукції"),
    ],
    "amr_03": [
        ("PICKUP_QC",    "load",    3.0, "Забір виробу з контролю якості"),
        ("DROPOFF_FIN_B","inspect", 4.0, "Приймання-контроль перед складуванням"),
        ("DROPOFF_FIN_B","unload",  2.0, "Складування на стелаж готової продукції"),
        ("PICKUP_QC",    "charge_check", 1.0, "Повернення до зони контролю якості"),
    ],
}


MQTT_PREFIX = {
    "amr_01": "factory/line_1/amr_01",
    "amr_02": "factory/line_1/amr_02",
    "amr_03": "factory/line_1/amr_03",
}


PREFERRED_DOCK = {
    "amr_01": "DOCK_CS01",
    "amr_02": "DOCK_CS02",
    "amr_03": "DOCK_CS03",
}


ZONES = {
    "warehouse_raw":    (0,  0,  10, 9),
    "corridor_main":    (10, 0,  13, 24),
    "assembly_a":       (13, 0,  23, 9),
    "corridor_mid":     (0,  9,  40, 11),
    "assembly_b":       (13, 11, 23, 24),
    "welding":          (23, 0,  32, 9),
    "packaging":        (23, 11, 32, 24),
    "charging":         (0,  11, 10, 15),
    "quality_control":  (0,  15, 10, 24),
    "warehouse_finished": (32, 0, 40, 24),
}


def zone_of(x: float, y: float) -> str:
    for name, (x0, y0, x1, y1) in ZONES.items():
        if x0 <= x <= x1 and y0 <= y <= y1:
            return name
    return "transit"


@dataclass
class Degradation:
    """Physically-motivated degradation for battery + motors.

    Models injected failure modes so the predictive-maintenance backend has
    realistic signals to detect (see inject_fault)."""
    robot_id: str
    soc:            float = 100.0
    soh:            float = 100.0
    voltage:        float = 25.2
    current:        float = 0.0
    battery_temp:   float = 25.0
    cycles:         int   = 0
    internal_r:     float = 0.05
    charging:       bool  = False

    left_temp:      float = 30.0
    right_temp:     float = 30.0
    left_vib:       float = 0.1
    right_vib:      float = 0.1
    left_eff:       float = 0.95
    right_eff:      float = 0.95
    total_hours:    float = 0.0

    bearing_wear_left:  float = 0.0
    bearing_wear_right: float = 0.0
    encoder_slip_left:  float = 0.0
    encoder_slip_right: float = 0.0


    fault_bearing_right:  bool = False
    fault_thermal_left:   bool = False
    fault_battery_fade:   bool = False
    fault_encoder_drift:  bool = False
    fault_brake_stuck:    bool = False

    def __post_init__(self):

        if self.robot_id == "amr_02":
            self.fault_bearing_right = True
            self.right_vib = 0.30
            self.right_eff = 0.88
        if self.robot_id == "amr_03":
            self.fault_battery_fade = True
            self.soh = 83.0


    def update(self, dt: float, left_cmd: float, right_cmd: float, moving: bool) -> None:
        if self.charging:
            self.soc = min(100.0, self.soc + (25.0 / 60.0) * dt * (self.soh / 100.0))
            self.current = -4.0
            self.voltage = 21.0 + (self.soc / 100.0) * 4.2
            self.battery_temp += (28.0 - self.battery_temp) * 0.02 * dt
            if self.soc >= FULL_SOC_PCT:
                self.charging = False
                self.cycles += 1
            return

        load = (abs(left_cmd) + abs(right_cmd)) / (2 * MAX_SPEED) if MAX_SPEED > 0 else 0
        self.current = 2.0 + load * 8.0

        fade_mult = 2.0 if self.fault_battery_fade else 1.0
        soc_drop = self.current * dt / (3600.0 * 5.0) * 100.0 / max(self.soh / 100.0, 0.1)
        self.soc = max(0.0, self.soc - soc_drop * fade_mult)
        self.voltage = 21.0 + (self.soc / 100.0) * 4.2
        if self.fault_battery_fade:

            self.voltage -= load * 0.6


        heat = self.current ** 2 * self.internal_r * 0.03
        if self.fault_battery_fade:
            heat += 0.6
        self.battery_temp += (heat - (self.battery_temp - 25.0) * 0.02) * dt
        self.battery_temp = max(22.0, min(70.0, self.battery_temp))

        self.soh = max(40.0, self.soh - 0.00002 * dt * (load + (0.5 if self.fault_battery_fade else 0)))
        self.internal_r = min(0.5, self.internal_r + 0.0000015 * dt * (2.0 if self.fault_battery_fade else 1.0))

        if moving:
            self.total_hours += dt / 3600.0

            l_heat = (abs(left_cmd) / MAX_SPEED) ** 2 * 0.8
            r_heat = (abs(right_cmd) / MAX_SPEED) ** 2 * 0.8
            if self.fault_thermal_left:
                l_heat *= 2.2
            self.left_temp  += (l_heat - (self.left_temp  - 30.0) * 0.01) * dt
            self.right_temp += (r_heat - (self.right_temp - 30.0) * 0.01) * dt
            self.left_temp  = max(25.0, min(100.0, self.left_temp))
            self.right_temp = max(25.0, min(100.0, self.right_temp))


            self.bearing_wear_left  += (0.000005 + (0.0001 if False else 0)) * dt * (abs(left_cmd) / MAX_SPEED)
            bw_r_rate = 0.000005 + (0.00015 if self.fault_bearing_right else 0)
            self.bearing_wear_right += bw_r_rate * dt * (abs(right_cmd) / MAX_SPEED)


            self.left_vib  = max(0.05, min(2.0, 0.10 + self.bearing_wear_left  * 4.0 + random.gauss(0, 0.02)))
            self.right_vib = max(0.05, min(2.0, 0.10 + self.bearing_wear_right * 4.0 + random.gauss(0, 0.02)))
            if self.fault_bearing_right:

                self.right_vib += 0.15 * abs(math.sin(time.time() * 12.0))


            self.left_eff  = max(0.55, 0.95 - (self.left_temp  - 30) / 200 - self.bearing_wear_left  * 0.5)
            self.right_eff = max(0.55, 0.95 - (self.right_temp - 30) / 200 - self.bearing_wear_right * 0.5)


            if self.fault_encoder_drift:
                self.encoder_slip_left  += random.gauss(0, 0.002) * dt
                self.encoder_slip_right += random.gauss(0, 0.002) * dt
        else:
            self.left_temp  += (30.0 - self.left_temp)  * 0.03 * dt
            self.right_temp += (30.0 - self.right_temp) * 0.03 * dt


def bfs_path(start: str, goal: str) -> List[str]:
    """Shortest path over NEIGHBOURS (unweighted BFS).  Returns [] if unreachable."""
    if start == goal:
        return [start]
    visited = {start}
    queue: deque = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        for nb in NEIGHBOURS.get(node, []):
            if nb in visited:
                continue
            if nb == goal:
                return path + [nb]
            visited.add(nb)
            queue.append((nb, path + [nb]))
    return []


def nearest_node(x: float, y: float) -> str:
    return min(NODES.keys(), key=lambda n: math.hypot(NODES[n][0] - x, NODES[n][1] - y))


def heading_from_compass(compass: Tuple[float, float, float]) -> float:
    """Heading in radians (0 = +X East, +π/2 = +Y North).  ENU Webots convention."""
    return math.atan2(compass[0], compass[1])


def wrap_angle(a: float) -> float:
    while a >  math.pi: a -= 2 * math.pi
    while a < -math.pi: a += 2 * math.pi
    return a


class AMR:
    def __init__(self) -> None:
        self.bot = Robot()
        self.dt_ms = int(self.bot.getBasicTimeStep())
        self.dt = self.dt_ms / 1000.0
        self.name = self.bot.getName()
        self.rid = self.bot.getCustomData() or self.name.lower().replace("-", "_")


        self.lm = self.bot.getDevice("left wheel motor")
        self.rm = self.bot.getDevice("right wheel motor")
        self.lm.setPosition(float("inf")); self.rm.setPosition(float("inf"))
        self.lm.setVelocity(0); self.rm.setVelocity(0)
        self.le = self.bot.getDevice("left wheel sensor")
        self.re = self.bot.getDevice("right wheel sensor")
        self.le.enable(self.dt_ms); self.re.enable(self.dt_ms)


        self.gps = self._enable("gps")
        self.compass = self._enable("compass")
        self.imu = self._enable("imu")
        self.accel = self._enable("accelerometer")
        self.gyro = self._enable("gyro")


        self.sonars: Dict[str, object] = {}
        for name in ["ds_0", "ds_45", "ds_90", "ds_135", "ds_180", "ds_225", "ds_270", "ds_315"]:
            d = self.bot.getDevice(name)
            if d is not None:
                d.enable(self.dt_ms)
                self.sonars[name] = d


        self.lidar = None
        try:
            self.lidar = self.bot.getDevice("lidar")
            if self.lidar:
                self.lidar.enable(self.dt_ms)

        except Exception:
            pass


        self.led = None
        try:
            self.led = self.bot.getDevice("status_led")
        except Exception:
            pass


        self.mission = MISSIONS.get(self.rid, MISSIONS["amr_01"])
        self.step_idx = 0
        self.cycle = 0
        self.state = "warmup"
        self.path: List[str] = []
        self.path_target_node: Optional[str] = None
        self.work_until: float = 0.0


        self.last_pos = (0.0, 0.0)
        self.last_pos_t = 0.0
        self.recoveries = 0
        self.recovery_until = 0.0
        self.recovery_dir = 1


        self.deg = Degradation(self.rid)
        self.odo = 0.0
        self.prev_le: Optional[float] = None
        self.prev_re: Optional[float] = None
        self.sim_t = 0.0
        self.last_tel_t = 0.0
        self.last_cmd_t = 0.0


        self.mqtt = None
        if not MQTT_ENABLED:
            print(f"[{self.name}] MQTT disabled (set AMR_MQTT=1 to enable).")
        if MQTT_ENABLED:
            try:
                import paho.mqtt.client as mqtt
                try:
                    self.mqtt = mqtt.Client(
                        mqtt.CallbackAPIVersion.VERSION1,
                        client_id=f"{self.rid}_controller",
                        clean_session=True,
                        protocol=mqtt.MQTTv311,
                    )
                except (AttributeError, TypeError):
                    self.mqtt = mqtt.Client(
                        client_id=f"{self.rid}_controller",
                        clean_session=True,
                        protocol=mqtt.MQTTv311,
                    )
                self.mqtt.on_message = self._on_mqtt_msg
                self.mqtt.reconnect_delay_set(min_delay=1, max_delay=30)
                self.mqtt.connect(MQTT_BROKER, MQTT_PORT, 60)
                self.mqtt.subscribe(f"{MQTT_PREFIX[self.rid]}/commands", qos=1)
                self.mqtt.loop_start()
                print(f"[{self.name}] MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
            except Exception as exc:
                print(f"[{self.name}] MQTT setup failed: {exc}")

        print(f"[{self.name}] ready | {len(self.mission)} mission steps | rid={self.rid}")


    def _enable(self, name: str):
        d = self.bot.getDevice(name)
        if d is not None:
            d.enable(self.dt_ms)
        return d


    def _on_mqtt_msg(self, client, userdata, msg):
        """Handle commands published by the backend.

        Supported:
          stop / emergency_stop          — halt motors, force ``idle`` state
          resume                         — leave idle, plan to current goal
          return_to_charge               — divert to nearest dock
          inject_fault {fault, enable}   — toggle a simulated fault
          clear_fault                    — clear all injected faults
          mission {action, mission_id}   — log; mission graph is hardcoded
        """
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        cmd = payload.get("command")
        try:
            if cmd in ("stop", "emergency_stop"):
                self.state = "idle"
                self._stop()
                print(f"[{self.name}] cmd={cmd} → idle")
            elif cmd == "resume":
                if self.state == "idle":
                    target_node, _, _, _ = self.cur_step()
                    self._plan_path_to(target_node)
                    self.state = "navigating"
                    print(f"[{self.name}] cmd=resume → navigating")
            elif cmd == "return_to_charge":


                requested = payload.get("dock_node")
                if requested and requested in NODES:
                    best = requested
                else:
                    best = PREFERRED_DOCK.get(self.rid)
                    if not best:

                        x, y = self.pos()
                        docks = ("DOCK_CS01", "DOCK_CS02", "DOCK_CS03")
                        best = min(docks,
                                   key=lambda n: math.hypot(NODES[n][0]-x, NODES[n][1]-y))
                self._plan_path_to(best)
                self.state = "docking"
                print(f"[{self.name}] cmd=return_to_charge → docking via {best}"
                      f"{' (assigned by backend)' if requested else ' (preferred fallback)'}")
            elif cmd == "inject_fault":
                fault = payload.get("fault")
                enable = bool(payload.get("enable", True))
                if fault in ("bearing_right", "thermal_left", "battery_fade",
                             "encoder_drift", "brake_stuck"):
                    setattr(self.deg, f"fault_{fault}", enable)
                    print(f"[{self.name}] FAULT '{fault}' → {enable}")
            elif cmd == "clear_fault":
                for f in ("bearing_right", "thermal_left", "battery_fade",
                          "encoder_drift", "brake_stuck"):
                    setattr(self.deg, f"fault_{f}", False)
                print(f"[{self.name}] all faults cleared")
            elif cmd == "mission":
                action = payload.get("action", "assigned")
                mid    = payload.get("mission_id", "?")
                print(f"[{self.name}] mission {mid} {action}")
            else:
                print(f"[{self.name}] unknown cmd: {cmd}")
        except Exception as exc:
            print(f"[{self.name}] cmd error: {exc}")


    def pos(self) -> Tuple[float, float]:
        v = self.gps.getValues()
        return v[0], v[1]

    def heading(self) -> float:
        return heading_from_compass(self.compass.getValues())

    def cur_step(self):
        return self.mission[self.step_idx % len(self.mission)]

    def _stop(self):
        self.lm.setVelocity(0); self.rm.setVelocity(0)

    def _set_wheels(self, left_cmd: float, right_cmd: float) -> Tuple[float, float]:

        left_cmd  *= self.deg.left_eff
        right_cmd *= self.deg.right_eff
        if self.deg.fault_brake_stuck:
            right_cmd *= 0.3
        left_cmd  = max(-MAX_SPEED, min(MAX_SPEED, left_cmd))
        right_cmd = max(-MAX_SPEED, min(MAX_SPEED, right_cmd))
        self.lm.setVelocity(left_cmd)
        self.rm.setVelocity(right_cmd)
        return left_cmd, right_cmd

    def _led_for_state(self):
        if not self.led:
            return
        if self.state in ("charging", "docking"):
            self.led.set(3)
        elif self.state == "working":
            self.led.set(1)
        elif self.deg.soc < LOW_SOC_PCT:
            self.led.set(2)
        else:
            self.led.set(0)


    def _forward_clearance(self) -> float:
        fronts = []
        for name in ("ds_0", "ds_45", "ds_315"):
            s = self.sonars.get(name)
            if s:
                v = s.getValue() / 1000.0

                fronts.append(max(0.0, v))
        clearance = min(fronts) if fronts else 5.0

        if self.lidar:
            rng = self.lidar.getRangeImage()
            if rng:
                n = len(rng)
                mid = n // 2
                half = max(1, n // 18)

                window = rng[mid - half:mid + half]
                window = [r for r in window if not math.isinf(r) and not math.isnan(r)]
                if window:
                    clearance = min(clearance, min(window))
        return clearance

    def _lateral_clearance(self, side: str) -> float:
        """side = 'left' or 'right' — returns min distance on that side."""
        if side == "left":
            names = ("ds_45", "ds_90", "ds_135")
        else:
            names = ("ds_225", "ds_270", "ds_315")
        vals = []
        for n in names:
            s = self.sonars.get(n)
            if s:
                vals.append(s.getValue() / 1000.0)
        return min(vals) if vals else 2.0


    def _steer_to(self, tx: float, ty: float) -> Tuple[float, float]:
        x, y = self.pos()
        dx, dy = tx - x, ty - y
        dist = math.hypot(dx, dy)
        desired = math.atan2(dy, dx)
        err = wrap_angle(desired - self.heading())

        clearance = self._forward_clearance()


        if clearance < OBSTACLE_CLOSE_M:
            left_c = self._lateral_clearance("left")
            right_c = self._lateral_clearance("right")
            turn = CRUISE_SPEED * 0.6
            if left_c >= right_c:
                return self._set_wheels(-turn, +turn)
            else:
                return self._set_wheels(+turn, -turn)


        base = min(CRUISE_SPEED, CRUISE_SPEED * (0.35 + 0.65 * min(dist / 1.2, 1.0)))
        if clearance < OBSTACLE_SLOW_M:
            base *= max(0.3, (clearance - OBSTACLE_CLOSE_M) / (OBSTACLE_SLOW_M - OBSTACLE_CLOSE_M))

            left_c = self._lateral_clearance("left")
            right_c = self._lateral_clearance("right")
            if right_c < left_c:
                err += 0.2
            else:
                err -= 0.2


        if abs(err) > math.radians(45):

            turn = CRUISE_SPEED * 0.55 * (1 if err > 0 else -1)
            return self._set_wheels(-turn, +turn)


        turn_bias = 4.0 * err
        left  = base - turn_bias
        right = base + turn_bias
        return self._set_wheels(left, right)

    def _reverse(self) -> Tuple[float, float]:
        sp = CRUISE_SPEED * 0.55
        return self._set_wheels(-sp + self.recovery_dir * sp * 0.5,
                                -sp - self.recovery_dir * sp * 0.5)

    def _odometry(self):
        l = self.le.getValue() + self.deg.encoder_slip_left
        r = self.re.getValue() + self.deg.encoder_slip_right
        if self.prev_le is not None:
            self.odo += abs(((l - self.prev_le) + (r - self.prev_re)) * WHEEL_R) / 2
        self.prev_le = l
        self.prev_re = r


    def _check_stuck(self) -> bool:
        now = self.sim_t
        x, y = self.pos()
        if now - self.last_pos_t < STUCK_TIME:
            return False
        moved = math.hypot(x - self.last_pos[0], y - self.last_pos[1])
        self.last_pos = (x, y)
        self.last_pos_t = now
        if moved < STUCK_DIST:
            self.recoveries += 1
            print(f"[{self.name}] STUCK #{self.recoveries} at ({x:.1f},{y:.1f}); recovery")
            if self.recoveries >= MAX_RECOVERIES:

                if self.path:
                    print(f"[{self.name}] Skipping unreachable node {self.path[0]}")
                    self.path.pop(0)
                self.recoveries = 0
            else:
                self.recovery_until = now + RECOVERY_TIME
                self.recovery_dir *= -1
            return True
        self.recoveries = 0
        return False


    def _plan_path_to(self, goal_node: str):
        start_node = nearest_node(*self.pos())
        self.path = bfs_path(start_node, goal_node)
        self.path_target_node = goal_node
        if not self.path:
            print(f"[{self.name}] NO PATH from {start_node} to {goal_node}")
        else:
            print(f"[{self.name}] route {start_node} → {goal_node}: {' → '.join(self.path)}")


    def _build_telemetry(self) -> dict:
        x, y = self.pos()
        hdg = math.degrees(self.heading()) % 360
        im = self.imu.getRollPitchYaw()
        ac = self.accel.getValues()
        gy = self.gyro.getValues()
        step = self.cur_step()


        nearest = 99.0
        nearest_dir = "none"
        for name, s in self.sonars.items():
            v = s.getValue() / 1000.0
            if v < nearest:
                nearest = v
                nearest_dir = name

        d = self.deg
        return {
            "robot_id": self.rid,
            "ts": self.sim_t,
            "battery": {
                "soc": round(d.soc, 2),
                "soh": round(d.soh, 2),
                "voltage": round(d.voltage, 2),
                "current": round(d.current, 2),
                "temperature": round(d.battery_temp, 1),
                "internal_resistance": round(d.internal_r, 4),
                "cycles": d.cycles,
                "is_charging": d.charging,
            },
            "motors": {
                "left":  {"temperature": round(d.left_temp, 1),
                          "vibration":   round(d.left_vib, 3),
                          "efficiency":  round(d.left_eff, 3),
                          "bearing_wear": round(d.bearing_wear_left, 4)},
                "right": {"temperature": round(d.right_temp, 1),
                          "vibration":   round(d.right_vib, 3),
                          "efficiency":  round(d.right_eff, 3),
                          "bearing_wear": round(d.bearing_wear_right, 4)},
                "hours": round(d.total_hours, 3),
            },
            "position": {"x": round(x, 3), "y": round(y, 3),
                         "heading": round(hdg, 1), "zone": zone_of(x, y)},
            "imu": {"roll":  round(im[0], 4),
                    "pitch": round(im[1], 4),
                    "yaw":   round(im[2], 4),
                    "accel_x": round(ac[0], 3),
                    "accel_y": round(ac[1], 3),
                    "accel_z": round(ac[2], 3),
                    "gyro_z": round(gy[2], 4)},
            "environment": {"nearest_obstacle_m": round(nearest, 2),
                            "nearest_obstacle_dir": nearest_dir},
            "mission": {"state": self.state,
                        "step":  self.step_idx,
                        "cycle": self.cycle,
                        "action": step[1],
                        "task":   step[3],
                        "odometry_m": round(self.odo, 2),
                        "sim_time_s": round(self.sim_t, 1)},
            "faults": {
                "bearing_right":  d.fault_bearing_right,
                "thermal_left":   d.fault_thermal_left,
                "battery_fade":   d.fault_battery_fade,
                "encoder_drift":  d.fault_encoder_drift,
                "brake_stuck":    d.fault_brake_stuck,
            },
        }

    def _publish_telemetry(self, tel: dict):
        if not self.mqtt:
            return
        base = MQTT_PREFIX[self.rid]
        for section in ("battery", "motors", "position", "imu", "environment", "mission", "faults"):
            self.mqtt.publish(f"{base}/telemetry/{section}",
                              json.dumps({"ts": tel["ts"], **tel[section]}), qos=0)


    def run(self):
        while self.bot.step(self.dt_ms) != -1:
            self.sim_t += self.dt
            self._odometry()
            self._led_for_state()


            if self.state == "warmup":
                self._stop()
                if self.sim_t >= SENSOR_WARMUP:
                    self.state = "navigating"
                    self.last_pos = self.pos()
                    self.last_pos_t = self.sim_t
                    target_node, _, _, _ = self.cur_step()
                    self._plan_path_to(target_node)
                self.deg.update(self.dt, 0, 0, False)
                continue

            if self.state == "idle":
                self._stop()
                self.deg.update(self.dt, 0, 0, False)
                self._maybe_telemetry()
                continue


            if self.sim_t < self.recovery_until:
                l, r = self._reverse()
                self.deg.update(self.dt, l, r, True)
                self._maybe_telemetry()
                continue


            if (self.state not in ("charging", "docking") and
                self.deg.soc < LOW_SOC_PCT and not self.deg.charging):
                print(f"[{self.name}] LOW BATTERY {self.deg.soc:.0f}% → go charge")
                self.state = "docking"
                best = PREFERRED_DOCK.get(self.rid)
                if not best:
                    x, y = self.pos()
                    docks = ("DOCK_CS01", "DOCK_CS02", "DOCK_CS03")
                    best = min(docks, key=lambda n: math.hypot(NODES[n][0]-x, NODES[n][1]-y))
                self._plan_path_to(best)


            if self.state == "working":
                self._stop()
                if self.sim_t >= self.work_until:
                    s = self.cur_step()
                    print(f"[{self.name}] ✓ {s[3]}")
                    self.step_idx = (self.step_idx + 1) % len(self.mission)
                    if self.step_idx == 0:
                        self.cycle += 1
                        print(f"[{self.name}] ══ Cycle {self.cycle} complete ══")
                    next_node, _, _, _ = self.cur_step()
                    self._plan_path_to(next_node)
                    self.state = "navigating"
                self.deg.update(self.dt, 0, 0, False)
                self._maybe_telemetry()
                continue


            if self.state == "charging":
                self._stop()
                if not self.deg.charging:
                    print(f"[{self.name}] charge complete SoC={self.deg.soc:.0f}%")

                    next_node, _, _, _ = self.cur_step()
                    self._plan_path_to(next_node)
                    self.state = "navigating"
                self.deg.update(self.dt, 0, 0, False)
                self._maybe_telemetry()
                continue


            if self.state == "docking":
                if not self.path:

                    self._stop()
                    self.deg.charging = True
                    self.state = "charging"
                    print(f"[{self.name}] docked & charging…")
                    continue
                self._advance_along_path(dock=True)
                self._maybe_telemetry()
                continue


            if self.state == "navigating":
                if not self.path:

                    s = self.cur_step()
                    if s[1] == "move":
                        self.step_idx = (self.step_idx + 1) % len(self.mission)
                        if self.step_idx == 0:
                            self.cycle += 1
                        next_node, _, _, _ = self.cur_step()
                        self._plan_path_to(next_node)
                    else:
                        self.work_until = self.sim_t + s[2]
                        self.state = "working"
                        print(f"[{self.name}] ▶ {s[3]} ({s[2]:.0f}s)")
                    self.deg.update(self.dt, 0, 0, False)
                    self._maybe_telemetry()
                    continue
                self._advance_along_path(dock=False)
                self._maybe_telemetry()


    def _advance_along_path(self, dock: bool):
        target_node = self.path[0]
        tx, ty = NODES[target_node]
        x, y = self.pos()
        dist = math.hypot(tx - x, ty - y)
        tol = DOCK_TOLERANCE if (dock and target_node.startswith("DOCK_")) else WP_TOLERANCE
        if dist < tol:
            self.path.pop(0)
            return
        if self._check_stuck():
            return
        l, r = self._steer_to(tx, ty)
        self.deg.update(self.dt, l, r, True)

    def _maybe_telemetry(self):
        if self.sim_t - self.last_tel_t < TELEMETRY_INTERVAL:
            return
        self.last_tel_t = self.sim_t
        tel = self._build_telemetry()

        x, y = self.pos()
        step = self.cur_step()
        act = step[1].upper()
        print(f"[{self.name}] ({x:5.1f},{y:5.1f}) {zone_of(x,y):18s} "
              f"SoC={self.deg.soc:5.1f}% SoH={self.deg.soh:5.1f}% "
              f"T={self.deg.left_temp:4.0f}/{self.deg.right_temp:4.0f}°C "
              f"vib={self.deg.right_vib:.2f} odo={self.odo:6.1f}m "
              f"cyc={self.cycle} | {act} {step[3]}")
        self._publish_telemetry(tel)


if __name__ == "__main__":
    AMR().run()

export type Role = "admin" | "engineer" | "operator";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  department?: string;
  position_title?: string;
  is_active: boolean;
  last_login_at?: string;
  created_at: string;
}

export interface Robot {
  id: string;
  code: string;
  model: string;
  status: string;
  last_x: number | null;
  last_y: number | null;
  last_zone: string | null;
  last_seen_at: string | null;
  firmware_version: string;
}

export interface RobotComponent {
  id: string;
  category: string;
  name: string;
  position_label: string | null;
  part_number: string | null;
  current_soh_pct: number | null;
  expected_life_hours: number | null;
  current_hours: number;
}

export interface RobotDetail extends Robot {
  serial_number: string;
  mqtt_client_id: string;
  total_odometry_m: number;
  total_missions: number;
  components: RobotComponent[];
}

export interface Telemetry {
  id: string;
  robot_id: string;
  recorded_at: string;
  pos_x: number | null;
  pos_y: number | null;
  heading_deg: number | null;
  zone: string | null;
  battery_soc: number | null;
  battery_soh: number | null;
  battery_voltage: number | null;
  battery_current: number | null;
  battery_temp: number | null;
  left_motor_temp: number | null;
  right_motor_temp: number | null;
  left_motor_vib: number | null;
  right_motor_vib: number | null;
  odometry_m: number | null;
  state: string | null;
}

export interface TelemetrySeriesPoint { t: string; value: number; }

export interface AlertRule {
  id: string;
  name: string;
  parameter: string;
  operator: string;
  threshold: number;
  severity: string;
  description: string | null;
  is_enabled: boolean;

  mode: "static" | "adaptive";
  window_minutes: number;
  k_sigma: number;
  created_at: string;
}

export interface Anomaly {
  id: string;
  robot_id: string;
  severity: string;
  parameter: string;
  value: number;
  threshold: number;
  message: string;
  detected_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  acknowledged_by_name: string | null;
  resolved_at: string | null;
}

export interface Ticket {
  id: string;
  robot_id: string;
  component_id: string | null;
  anomaly_id: string | null;
  title: string;
  description: string | null;
  maintenance_type: string;
  priority: string;
  status: string;
  created_by: string | null;
  assigned_to: string | null;
  estimated_hours: number | null;
  actual_hours: number | null;
  sla_deadline: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  comments: TicketComment[];
}

export interface TicketComment {
  id: string;
  user_id: string | null;
  body: string;
  created_at: string;
}

export interface Mission {
  id: string;
  robot_id: string | null;
  origin_zone_id: string | null;
  destination_zone_id: string | null;
  payload_type: string | null;
  payload_weight_kg: number | null;
  status: string;
  priority: string;
  mes_order_id: string | null;
  notes: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ComponentHealth {
  component_id: string;
  category: string;
  name: string;
  health_score: number;
  soh_pct: number | null;
  degradation_trend: "stable" | "improving" | "degrading" | "critical";
  notes: string;
}

export interface RulPrediction {
  robot_id: string;
  component_id: string;
  component_name: string;
  predicted_rul_hours: number;
  confidence: number;
  recommendation: string;
  predicted_at: string;
  model?: "heuristic" | "linear_regression";
  r2_score?: number | null;
  soh_slope_pct_per_day?: number | null;
  days_to_replacement?: number | null;
  replacement_threshold_pct?: number | null;
}

export interface SohForecastPoint { t: string; soh_pct: number; is_forecast: boolean; }

export interface SohForecast {
  robot_id: string;
  component_id: string;
  history: SohForecastPoint[];
  forecast: SohForecastPoint[];
  intercept_pct: number;
  slope_pct_per_day: number;
  r2_score: number;
  replacement_threshold_pct: number;
  days_to_replacement: number | null;
  n_samples: number;
}

export interface KpiSnapshot {
  period_from: string;
  period_to: string;
  total_robots: number;
  fleet_availability_pct: number;
  fleet_oee_pct: number;
  mtbf_hours: number;
  mttr_hours: number;
  anomalies_total: number;
  anomalies_critical: number;
  tickets_open: number;
  tickets_resolved: number;
  unplanned_downtime_hours: number;
  missions_completed: number;
  per_robot: KpiPerRobot[];
}

export interface KpiPerRobot {
  robot_id: string;
  code: string;
  availability_pct: number;
  active_hours: number;
  charging_hours: number;
  idle_hours: number;
  failed_hours: number;
  missions_completed: number;
  anomalies: number;
  mtbf_hours: number | null;
  mttr_hours: number | null;
}

export interface FleetSummaryItem { robot_id: string; code: string; health_score: number; }

export interface Zone {
  id: string;
  line_id: string;
  name: string;
  zone_type: string;
  color_hex: string;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface ChargingStation {
  id: string;
  code: string;
  x_position: number;
  y_position: number;
  max_power_w: number;
  is_occupied: boolean;
}

export interface ProductionLineRef {
  id: string;
  factory_id: string;
  name: string;
  code: string;
  description: string | null;
}

export interface FactoryRef {
  id: string;
  name: string;
  code: string;
  city: string | null;
}

export interface FactoryLayout {
  factories: FactoryRef[];
  lines: ProductionLineRef[];
  zones: Zone[];
  chargers: ChargingStation[];
}

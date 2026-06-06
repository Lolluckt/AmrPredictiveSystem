import { api } from "./client";
import type {
  AlertRule, Anomaly, ComponentHealth, FactoryLayout, FleetSummaryItem,
  KpiSnapshot, Mission, Robot, RobotDetail, RulPrediction, SohForecast,
  Telemetry, TelemetrySeriesPoint, Ticket, TicketComment, User, Zone,
} from "@/types";

export const login = (email: string, password: string) =>
  api.post<{ access_token: string; refresh_token: string }>(
    "/auth/login", { email, password }
  ).then(r => r.data);
export const me = () => api.get<User>("/auth/me").then(r => r.data);

export const listUsers = () => api.get<User[]>("/users").then(r => r.data);
export const createUser = (payload: Partial<User> & { password: string }) =>
  api.post<User>("/users", payload).then(r => r.data);
export const updateUser = (id: string, payload: Partial<User> & { password?: string }) =>
  api.patch<User>(`/users/${id}`, payload).then(r => r.data);
export const deleteUser = (id: string) => api.delete(`/users/${id}`);

export const listRobots = () => api.get<Robot[]>("/robots").then(r => r.data);
export const getRobot = (id: string) => api.get<RobotDetail>(`/robots/${id}`).then(r => r.data);
export const sendCommand = (id: string, command: string, params: Record<string, unknown> = {}) =>
  api.post(`/robots/${id}/command`, { command, params }).then(r => r.data);

export const latestTelemetry = (robotId: string) =>
  api.get<Telemetry | null>(`/telemetry/${robotId}/latest`).then(r => r.data);
export const latestTelemetryAll = () =>
  api.get<Telemetry[]>(`/telemetry/latest`).then(r => r.data);
export const telemetryHistory = (robotId: string, limit = 200) =>
  api.get<Telemetry[]>(`/telemetry/${robotId}/history`, { params: { limit } }).then(r => r.data);
export const telemetrySeries = (robotId: string, field: string, limit = 300) =>
  api.get<TelemetrySeriesPoint[]>(`/telemetry/${robotId}/series`,
    { params: { field, limit } }).then(r => r.data);

export const listRules = () => api.get<AlertRule[]>("/alert-rules").then(r => r.data);
export const createRule = (p: Omit<AlertRule, "id" | "created_at">) =>
  api.post<AlertRule>("/alert-rules", p).then(r => r.data);
export const updateRule = (id: string, p: Omit<AlertRule, "id" | "created_at">) =>
  api.patch<AlertRule>(`/alert-rules/${id}`, p).then(r => r.data);
export const deleteRule = (id: string) => api.delete(`/alert-rules/${id}`);
export const listAnomalies = (params: { robot_id?: string; unresolved?: boolean } = {}) =>
  api.get<Anomaly[]>("/anomalies", { params }).then(r => r.data);
export const acknowledgeAnomaly = (id: string) =>
  api.post<Anomaly>(`/anomalies/${id}/ack`).then(r => r.data);
export const resolveAnomaly = (id: string) =>
  api.post<Anomaly>(`/anomalies/${id}/resolve`).then(r => r.data);
export const createTicketFromAnomaly = (id: string) =>
  api.post<Ticket>(`/anomalies/${id}/ticket`).then(r => r.data);

export const listTickets = (params: { status?: string; robot_id?: string } = {}) =>
  api.get<Ticket[]>("/tickets", { params }).then(r => r.data);
export const getTicket = (id: string) => api.get<Ticket>(`/tickets/${id}`).then(r => r.data);
export const createTicket = (p: Partial<Ticket> & { title: string; robot_id: string }) =>
  api.post<Ticket>("/tickets", p).then(r => r.data);
export const updateTicket = (id: string, p: Partial<Ticket>) =>
  api.patch<Ticket>(`/tickets/${id}`, p).then(r => r.data);
export const addTicketComment = (id: string, body: string) =>
  api.post<TicketComment>(`/tickets/${id}/comments`, { body }).then(r => r.data);

export const listMissions = (params: { status?: string; robot_id?: string } = {}) =>
  api.get<Mission[]>("/missions", { params }).then(r => r.data);
export const createMission = (p: Partial<Mission>) =>
  api.post<Mission>("/missions", p).then(r => r.data);
export const updateMission = (id: string, p: Partial<Mission>) =>
  api.patch<Mission>(`/missions/${id}`, p).then(r => r.data);
export const cancelMission = (id: string) =>
  api.post<Mission>(`/missions/${id}/cancel`).then(r => r.data);

export const robotHealth = (id: string) =>
  api.get<ComponentHealth[]>(`/predictive/robots/${id}/health`).then(r => r.data);
export const robotRul = (id: string) =>
  api.get<RulPrediction[]>(`/predictive/robots/${id}/rul`).then(r => r.data);
export const fleetSummary = () =>
  api.get<FleetSummaryItem[]>("/predictive/fleet").then(r => r.data);
export const sohForecast = (id: string, params: {
  component_id?: string; threshold_pct?: number; horizon_days?: number;
} = {}) =>
  api.get<SohForecast>(`/predictive/robots/${id}/soh-forecast`, { params })
    .then(r => r.data);

export const kpiSnapshot = (params: {
  period?: "1h" | "24h" | "7d" | "30d";
  from?: string; to?: string; robot_id?: string;
} = {}) =>
  api.get<KpiSnapshot>("/analytics/kpi", { params }).then(r => r.data);

export async function downloadTelemetry(
  robotId: string, format: "csv" | "xlsx",
  params: { from?: string; to?: string } = {},
) {
  const res = await api.get(`/telemetry/${robotId}/export`, {
    params: { ...params, format },
    responseType: "blob",
  });
  const blob = res.data as Blob;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `telemetry_${robotId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const factoryLayout = () =>
  api.get<FactoryLayout>("/factory/layout").then(r => r.data);
export const listZones = () =>
  api.get<Zone[]>("/factory/zones").then(r => r.data);

export const apiMeta = () =>
  api.get<{ name: string; env: string; version: string; uptime_s: number;
            mqtt_enabled: boolean; mqtt_broker: string }>("/meta").then(r => r.data);

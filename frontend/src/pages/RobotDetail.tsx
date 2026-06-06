import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getRobot, latestTelemetry, telemetrySeries, robotHealth, robotRul, sendCommand,
  sohForecast, downloadTelemetry,
} from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { HealthPill, StatusBadge } from "@/components/StatusBadge";
import { useAuthStore } from "@/store/auth";
import { useToast } from "@/components/Toast";
import {
  LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceLine, Legend,
} from "recharts";

const SERIES_FIELDS: Array<{ field: string; label: string; color: string; unit?: string }> = [
  { field: "battery_soc",       label: "Заряд батареї (SoC)", color: "#2563eb", unit: "%" },
  { field: "battery_temp",      label: "Температура батареї", color: "#dc2626", unit: "°C" },
  { field: "left_motor_temp",   label: "T° лівого двигуна",   color: "#f97316", unit: "°C" },
  { field: "right_motor_temp",  label: "T° правого двигуна",  color: "#f59e0b", unit: "°C" },
  { field: "left_motor_vib",    label: "Вібрація лівого",     color: "#059669", unit: "g" },
  { field: "right_motor_vib",   label: "Вібрація правого",    color: "#16a34a", unit: "g" },
];

export default function RobotDetail() {
  const { id = "" } = useParams();
  const robot  = useQuery({ queryKey: ["robot", id],
                            queryFn: () => getRobot(id) });
  const latest = useQuery({ queryKey: ["telemetry", "latest", id],
                            queryFn: () => latestTelemetry(id) });
  const health = useQuery({ queryKey: ["predict", "health", id],
                            queryFn: () => robotHealth(id),
                            refetchInterval: 30_000 });
  const rul    = useQuery({ queryKey: ["predict", "rul", id],
                            queryFn: () => robotRul(id),
                            refetchInterval: 60_000 });
  const toast = useToast();

  const qc = useQueryClient();
  const canCommand = useAuthStore((s) =>
    s.user && ["admin", "engineer", "operator"].includes(s.user.role));
  const canFault   = useAuthStore((s) =>
    s.user && ["admin", "engineer"].includes(s.user.role));

  const cmd = useMutation({
    mutationFn: (v: { command: string; params?: Record<string, unknown> }) =>
      sendCommand(id, v.command, v.params),
    onSuccess: (data: any, vars) => {
      toast.show({
        tone: data.delivered ? "success" : "warning",
        title: `Команда: ${vars.command}`,
        body: data.delivered
          ? `Доставлено до ${data.robot}`
          : "MQTT недоступний — команду буде втрачено.",
      });
      qc.invalidateQueries({ queryKey: ["robot", id] });
    },
    onError: (err: any, vars) => toast.show({
      tone: "error",
      title: `Помилка ${vars.command}`,
      body: err?.response?.data?.error?.detail
            ?? err?.response?.data?.detail
            ?? "Сервер не зміг виконати команду.",
    }),
  });

  if (robot.isLoading) return <div className="p-6 text-slate-500">Завантаження…</div>;
  if (!robot.data) return <div className="p-6 text-rose-600">Робота не знайдено.</div>;

  const r = robot.data;

  return (
    <div className="p-6 space-y-4">
      <PageHeader
        title={`${r.code} · ${r.model}`}
        subtitle={`Serial ${r.serial_number} · FW ${r.firmware_version}`}
        actions={
          <>
            {canCommand && (
              <>
                <button className="btn-secondary" disabled={cmd.isPending}
                        onClick={() => cmd.mutate({ command: "stop" })}>Stop</button>
                <button className="btn-secondary" disabled={cmd.isPending}
                        onClick={() => cmd.mutate({ command: "resume" })}>Resume</button>
                <button className="btn-secondary" disabled={cmd.isPending}
                        onClick={() => cmd.mutate({ command: "return_to_charge" })}>На зарядку</button>
                <button className="btn-danger" disabled={cmd.isPending}
                        onClick={() => cmd.mutate({ command: "emergency_stop" })}>E-Stop</button>
              </>
            )}
            {}
            <button className="btn-secondary"
                    title="Експорт останніх 24 годин у CSV"
                    onClick={() => downloadTelemetry(id, "csv").catch((e) =>
                      toast.show({ tone: "error", title: "Експорт CSV не вдався",
                        body: e?.response?.status === 404 ? "Немає даних за період" : "" }))}>
              CSV
            </button>
            <button className="btn-secondary"
                    title="Експорт останніх 24 годин у XLSX"
                    onClick={() => downloadTelemetry(id, "xlsx").catch((e) =>
                      toast.show({ tone: "error", title: "Експорт XLSX не вдався",
                        body: e?.response?.status === 501 ? "openpyxl не встановлено" : "" }))}>
              XLSX
            </button>
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
        <MetricCard label="Статус"  value={<StatusBadge status={r.status} />} />
        <MetricCard label="Зона"    value={r.last_zone ?? "—"} />
        <MetricCard label="SoC"
                    value={latest.data?.battery_soc?.toFixed(0) ?? "—"} suffix="%" />
        <MetricCard label="Пробіг"  value={r.total_odometry_m.toFixed(0)} suffix=" м" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {SERIES_FIELDS.map(f => <MetricChart key={f.field} robotId={id} {...f} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="card p-4">
          <div className="text-sm font-semibold mb-2">Стан компонентів</div>
          <table className="w-full text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left">Компонент</th>
                <th className="text-left">SoH</th>
                <th className="text-left">Здоров'я</th>
                <th className="text-left">Коментар</th>
              </tr>
            </thead>
            <tbody>
              {(health.data ?? []).map(h => (
                <tr key={h.component_id} className="border-t border-slate-100">
                  <td className="py-2">
                    <div>{h.name}</div>
                    <div className="text-xs text-slate-500">{h.category}</div>
                  </td>
                  <td>{h.soh_pct != null ? `${h.soh_pct.toFixed(1)}%` : "—"}</td>
                  <td><HealthPill score={h.health_score} /></td>
                  <td className="text-slate-600 text-xs">{h.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card p-4">
          <div className="text-sm font-semibold mb-2">RUL — залишковий ресурс</div>
          <ul className="space-y-2 text-sm">
            {(rul.data ?? []).map(p => (
              <li key={p.component_id} className="border-b border-slate-100 pb-2">
                <div className="flex justify-between">
                  <div className="font-medium">{p.component_name}</div>
                  <div className="text-slate-600">
                    {p.predicted_rul_hours.toFixed(0)} год
                    {p.days_to_replacement != null && (
                      <span className="text-xs text-slate-500 ml-1">
                        (≈{p.days_to_replacement.toFixed(0)} днів)
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-xs text-slate-500">
                  Модель: <span className="font-mono">{p.model ?? "heuristic"}</span>
                  {p.r2_score != null && <> · R²={p.r2_score.toFixed(2)}</>}
                  {" · "}впевн. {(p.confidence * 100).toFixed(0)}%
                </div>
                <div className="text-xs text-slate-600 mt-0.5">{p.recommendation}</div>
              </li>
            ))}
            {(rul.data ?? []).length === 0 &&
              <li className="text-xs text-slate-500">Поки що недостатньо даних для прогнозу.</li>}
          </ul>
        </div>
      </div>

      {/* Прогноз SoH з лінійної регресії — окремий блок з графіком */}
      <SohForecastBlock robotId={id} />

      {canFault && (
        <div className="card p-4">
          <div className="text-sm font-semibold mb-2">
            Інжекція несправностей (для демонстрації PdM)
          </div>
          <div className="text-xs text-slate-500 mb-2">
            Натисніть ▶ щоб увімкнути симульовану несправність, ■ щоб вимкнути.
            Симулятор почне продукувати відповідну сигнатуру в телеметрії.
          </div>
          <div className="flex flex-wrap gap-2">
            {["bearing_right", "thermal_left", "battery_fade", "encoder_drift", "brake_stuck"].map(f => (
              <span key={f} className="inline-flex gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs">
                <span className="font-mono">{f}</span>
                <button className="text-emerald-600 font-bold"
                        onClick={() => cmd.mutate({ command: "inject_fault",
                                                    params: { fault: f, enable: true } })}>▶</button>
                <button className="text-rose-600 font-bold"
                        onClick={() => cmd.mutate({ command: "inject_fault",
                                                    params: { fault: f, enable: false } })}>■</button>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, suffix = "" }:
  { label: string; value: React.ReactNode; suffix?: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-semibold">{value}{suffix}</div>
    </div>
  );
}

function SohForecastBlock({ robotId }: { robotId: string }) {
  const fc = useQuery({
    queryKey: ["soh-forecast", robotId],
    queryFn: () => sohForecast(robotId, { threshold_pct: 70, horizon_days: 180 }),
    refetchInterval: 5 * 60_000,
    retry: false,
  });

  if (fc.isLoading) {
    return <div className="card p-4 text-sm text-slate-500">
      Обчислення прогнозу SoH…
    </div>;
  }
  if (fc.isError || !fc.data) {
    return <div className="card p-4 text-sm text-slate-500">
      Прогноз SoH не побудовано: недостатньо історії телеметрії або
      тренд незначущий (R²&lt;0.25). Запустіть симулятор на довшу зміну
      і повторіть.
    </div>;
  }

  const data = fc.data;
  // Об'єднати історію і прогноз у одну серію з двома значеннями (соlive/forecast)

  const merged = [
    ...data.history.map(p => ({
      t: new Date(p.t).toLocaleDateString(),
      historical: p.soh_pct, forecast: null as number | null,
    })),
    ...data.forecast.map(p => ({
      t: new Date(p.t).toLocaleDateString(),
      historical: null as number | null, forecast: p.soh_pct,
    })),
  ];

  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between mb-2">
        <div className="text-sm font-semibold">
          Прогноз SoH батареї (лінійна регресія)
        </div>
        <div className="text-xs text-slate-500">
          slope {data.slope_pct_per_day.toFixed(3)} %/добу
          {" · "}R² = {data.r2_score.toFixed(2)}
          {" · "}n = {data.n_samples}
        </div>
      </div>
      <div className="text-xs text-slate-600 mb-2">
        Поточний тренд: SoH знижується на
        {" "}<b>{Math.abs(data.slope_pct_per_day).toFixed(3)} %/добу</b>.
        {data.days_to_replacement != null
          ? <> Прогноз заміни через{" "}
              <b>{data.days_to_replacement.toFixed(0)} днів</b>{" "}
              (поріг {data.replacement_threshold_pct}%).</>
          : <> SoH ще вище порога {data.replacement_threshold_pct}%.</>}
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={merged} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="t" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} domain={[40, 100]} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={data.replacement_threshold_pct}
                           stroke="#dc2626" strokeDasharray="4 4"
                           label={{ value: `Поріг ${data.replacement_threshold_pct}%`,
                                     position: "insideTopRight",
                                     fontSize: 10, fill: "#dc2626" }} />
            <Line type="monotone" dataKey="historical" name="Історія SoH"
                  stroke="#2563eb" dot={false} strokeWidth={2}
                  isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="forecast" name="Регресійний прогноз"
                  stroke="#7c3aed" dot={false} strokeWidth={2}
                  strokeDasharray="5 5" isAnimationActive={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function MetricChart({ robotId, field, label, color, unit }:
  { robotId: string; field: string; label: string; color: string; unit?: string }) {
  const { data } = useQuery({
    queryKey: ["series", robotId, field],
    queryFn: () => telemetrySeries(robotId, field),
    refetchInterval: 10_000,
  });
  const formatted = (data ?? []).map(p => ({
    t: new Date(p.t).toLocaleTimeString().slice(0, 8),
    v: p.value,
  }));
  return (
    <div className="card p-4">
      <div className="text-sm font-medium mb-2">{label}
        {unit && <span className="text-slate-400 ml-1 text-xs">({unit})</span>}
      </div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={formatted} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="t" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Line type="monotone" dataKey="v" stroke={color}
                  dot={false} strokeWidth={2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

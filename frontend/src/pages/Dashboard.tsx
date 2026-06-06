
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  factoryLayout, fleetSummary, latestTelemetryAll,
  listAnomalies, listRobots, listTickets,
} from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { HealthPill, SeverityBadge, StatusBadge } from "@/components/StatusBadge";
import { FactoryMap } from "@/components/FactoryMap";
import { Bot, AlertTriangle, TicketCheck, Activity } from "lucide-react";

export default function Dashboard() {
  const robots  = useQuery({ queryKey: ["robots"],   queryFn: listRobots,
                             refetchInterval: 30_000 });
  const fleet   = useQuery({ queryKey: ["fleet"],    queryFn: fleetSummary,
                             refetchInterval: 60_000 });
  const alerts  = useQuery({ queryKey: ["anomalies", "unresolved"],
                             queryFn: () => listAnomalies({ unresolved: true }) });
  const tickets = useQuery({ queryKey: ["tickets", "open"],
                             queryFn: () => listTickets({ status: "in_progress" }) });
  const layout  = useQuery({ queryKey: ["layout"],   queryFn: factoryLayout,
                             staleTime: 5 * 60_000 });
  const tel     = useQuery({ queryKey: ["telemetry", "latest_all"],
                             queryFn: latestTelemetryAll });

  const healthByRobot = Object.fromEntries(
    (fleet.data ?? []).map(f => [f.robot_id, f.health_score]),
  );
  const onlineCount   = (robots.data ?? []).filter(
    r => r.status === "operational" || r.status === "charging").length;

  const meanHealth = fleet.data && fleet.data.length
    ? Math.round(fleet.data.reduce((s, f) => s + f.health_score, 0) / fleet.data.length)
    : 0;

  return (
    <div className="p-6">
      <PageHeader title="Огляд цеху"
                  subtitle="Поточний стан флоту AMR, відкриті інциденти та шопфлор у реальному часі" />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
        <KPI title="Роботи активні"
             value={onlineCount} total={(robots.data ?? []).length}
             icon={<Bot size={18} />} tone="ok" />
        <KPI title="Відкриті аномалії" value={alerts.data?.length ?? 0}
             tone={(alerts.data?.length ?? 0) > 0 ? "warning" : "ok"}
             icon={<AlertTriangle size={18} />} />
        <KPI title="Заявки в роботі"  value={tickets.data?.length ?? 0}
             icon={<TicketCheck size={18} />} />
        <KPI title="Середнє здоров'я" value={meanHealth}
             suffix="%" icon={<Activity size={18} />}
             tone={meanHealth >= 85 ? "ok" : meanHealth >= 65 ? "warning" : "critical"} />
      </div>

      <div className="mb-4">
        <FactoryMap layout={layout.data}
                    robots={robots.data ?? []}
                    telemetry={tel.data ?? []} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-4 lg:col-span-2">
          <div className="text-sm font-semibold mb-3">Флот AMR</div>
          <table className="w-full text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left">Робот</th>
                <th className="text-left">Статус</th>
                <th className="text-left">Зона</th>
                <th className="text-left">Позиція</th>
                <th className="text-left">Здоров'я</th>
              </tr>
            </thead>
            <tbody>
              {(robots.data ?? []).map(r => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="py-2">
                    <Link to={`/robots/${r.id}`} className="text-brand-600 hover:underline">
                      {r.code}
                    </Link>
                    <div className="text-xs text-slate-500">{r.model}</div>
                  </td>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="text-slate-600">{r.last_zone ?? "—"}</td>
                  <td className="text-slate-600">
                    {r.last_x != null
                      ? `${r.last_x.toFixed(1)}, ${r.last_y!.toFixed(1)}`
                      : "—"}
                  </td>
                  <td>
                    {healthByRobot[r.id] != null
                      ? <HealthPill score={healthByRobot[r.id]} />
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card p-4">
          <div className="text-sm font-semibold mb-3">Останні аномалії</div>
          <ul className="space-y-2 text-sm">
            {(alerts.data ?? []).slice(0, 8).map(a => (
              <li key={a.id} className="flex items-start gap-2">
                <SeverityBadge severity={a.severity} />
                <div className="flex-1 min-w-0">
                  <div className="truncate">{a.message}</div>
                  <div className="text-xs text-slate-500">
                    {new Date(a.detected_at).toLocaleString()}
                  </div>
                </div>
              </li>
            ))}
            {(alerts.data ?? []).length === 0 && (
              <div className="text-slate-500 text-sm">Активних аномалій немає.</div>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}

function KPI({ title, value, suffix = "", total, icon, tone }: {
  title: string;
  value: number;
  suffix?: string;
  total?: number;
  icon?: React.ReactNode;
  tone?: "ok" | "warning" | "critical";
}) {
  const bg =
    tone === "warning"  ? "bg-amber-50" :
    tone === "ok"       ? "bg-emerald-50" :
    tone === "critical" ? "bg-rose-50" :
                          "bg-white";
  return (
    <div className={`card p-4 ${bg}`}>
      <div className="flex items-center justify-between text-slate-500">
        <span className="text-xs">{title}</span>
        {icon}
      </div>
      <div className="text-2xl font-semibold mt-1">
        {value}{suffix}
        {total != null && <span className="text-sm text-slate-400"> / {total}</span>}
      </div>
    </div>
  );
}

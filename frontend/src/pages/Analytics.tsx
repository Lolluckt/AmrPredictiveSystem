import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { kpiSnapshot, listRobots } from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";

type Period = "1h" | "24h" | "7d" | "30d";
const PERIODS: { value: Period; label: string }[] = [
  { value: "1h",  label: "1 година" },
  { value: "24h", label: "24 години" },
  { value: "7d",  label: "7 днів" },
  { value: "30d", label: "30 днів" },
];

function KpiCard({ label, value, unit, tone = "default", hint }:
  { label: string; value: string | number; unit?: string;
    tone?: "default" | "good" | "warn" | "bad"; hint?: string }) {
  const toneCls =
    tone === "good" ? "text-emerald-700 bg-emerald-50 border-emerald-200" :
    tone === "warn" ? "text-amber-700  bg-amber-50  border-amber-200"  :
    tone === "bad"  ? "text-rose-700   bg-rose-50   border-rose-200"   :
                      "text-slate-800  bg-white     border-slate-200";
  return (
    <div className={`card p-4 border ${toneCls}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">{label}</div>
      <div className="mt-1 text-2xl font-bold">
        {value}
        {unit && <span className="text-base font-normal opacity-70 ml-1">{unit}</span>}
      </div>
      {hint && <div className="text-xs mt-1 opacity-60">{hint}</div>}
    </div>
  );
}

function avTone(pct: number): "good" | "warn" | "bad" {
  if (pct >= 90) return "good";
  if (pct >= 70) return "warn";
  return "bad";
}

export default function Analytics() {
  const [period, setPeriod] = useState<Period>("24h");
  const kpi = useQuery({
    queryKey: ["kpi", period],
    queryFn: () => kpiSnapshot({ period }),
    refetchInterval: 30_000,
  });
  const robots = useQuery({ queryKey: ["robots"], queryFn: listRobots });

  const data = kpi.data;

  return (
    <div className="p-6 space-y-4">
      <PageHeader
        title="Аналітика парку"
        subtitle="Інтегральні KPI: доступність, OEE, MTBF, MTTR, аномалії, тікети"
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Період:</span>
            {PERIODS.map(p => (
              <button key={p.value}
                onClick={() => setPeriod(p.value)}
                className={"px-3 py-1 text-xs rounded border " +
                  (period === p.value
                    ? "bg-brand-600 text-white border-brand-600"
                    : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50")}>
                {p.label}
              </button>
            ))}
          </div>
        }
      />

      {kpi.isLoading && <div className="text-slate-500">Завантаження…</div>}
      {kpi.isError   && <div className="text-rose-600">Помилка завантаження KPI.</div>}

      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Доступність флоту"
                     value={data.fleet_availability_pct.toFixed(1)}
                     unit="%"
                     tone={avTone(data.fleet_availability_pct)}
                     hint="Середнє по роботах за обраний період" />
            <KpiCard label="OEE"
                     value={data.fleet_oee_pct.toFixed(1)}
                     unit="%"
                     tone={avTone(data.fleet_oee_pct)}
                     hint="Availability × Performance × Quality" />
            <KpiCard label="MTBF"
                     value={data.mtbf_hours.toFixed(1)}
                     unit="год"
                     hint="Mean Time Between Failures" />
            <KpiCard label="MTTR"
                     value={data.mttr_hours.toFixed(1)}
                     unit="год"
                     tone={data.mttr_hours > 4 ? "warn" : "default"}
                     hint="Mean Time To Repair" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Аномалії за період"
                     value={data.anomalies_total}
                     tone={data.anomalies_critical > 0 ? "bad" : "default"}
                     hint={`з них critical/emergency: ${data.anomalies_critical}`} />
            <KpiCard label="Відкриті заявки"
                     value={data.tickets_open}
                     tone={data.tickets_open > 5 ? "warn" : "default"}
                     hint={`закрито за період: ${data.tickets_resolved}`} />
            <KpiCard label="Виконано місій"
                     value={data.missions_completed}
                     hint="Кумулятивно з телеметрії" />
            <KpiCard label="Незапланований простій"
                     value={data.unplanned_downtime_hours.toFixed(1)}
                     unit="год"
                     tone={data.unplanned_downtime_hours > 1 ? "bad" : "good"}
                     hint="Час у станах failed/critical" />
          </div>

          <div className="card overflow-hidden">
            <div className="px-4 py-2 border-b border-slate-200
                            text-sm font-semibold">Розклад по роботах</div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-left">
                <tr>
                  <th className="p-3">Робот</th>
                  <th className="p-3 text-right">Доступн.%</th>
                  <th className="p-3 text-right">Актив., год</th>
                  <th className="p-3 text-right">Зарядка, год</th>
                  <th className="p-3 text-right">Простій, год</th>
                  <th className="p-3 text-right">Аномалій</th>
                  <th className="p-3 text-right">MTBF, год</th>
                  <th className="p-3 text-right">MTTR, год</th>
                </tr>
              </thead>
              <tbody>
                {data.per_robot.map(p => {
                  const robot = robots.data?.find(r => r.id === p.robot_id);
                  const tone = avTone(p.availability_pct);
                  return (
                    <tr key={p.robot_id} className="border-t border-slate-100">
                      <td className="p-3">
                        <div className="font-medium">{p.code}</div>
                        {robot && <div className="text-xs text-slate-500">{robot.model}</div>}
                      </td>
                      <td className={"p-3 text-right font-semibold " + (
                        tone === "good" ? "text-emerald-700" :
                        tone === "warn" ? "text-amber-700" : "text-rose-700"
                      )}>{p.availability_pct.toFixed(1)}</td>
                      <td className="p-3 text-right">{p.active_hours.toFixed(1)}</td>
                      <td className="p-3 text-right">{p.charging_hours.toFixed(1)}</td>
                      <td className="p-3 text-right">{p.failed_hours.toFixed(1)}</td>
                      <td className="p-3 text-right">{p.anomalies}</td>
                      <td className="p-3 text-right">
                        {p.mtbf_hours !== null ? p.mtbf_hours.toFixed(1) : "—"}
                      </td>
                      <td className="p-3 text-right">
                        {p.mttr_hours !== null ? p.mttr_hours.toFixed(1) : "—"}
                      </td>
                    </tr>
                  );
                })}
                {data.per_robot.length === 0 && (
                  <tr><td colSpan={8} className="p-4 text-slate-500 text-center">
                    Немає даних за обраний період.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="text-xs text-slate-500">
            Період: {new Date(data.period_from).toLocaleString()} —
            {" "}{new Date(data.period_to).toLocaleString()}.
            Дані оновлюються автоматично кожні 30 с.
          </div>
        </>
      )}
    </div>
  );
}

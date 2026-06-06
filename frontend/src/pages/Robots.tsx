import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  fleetSummary, latestTelemetryAll, listRobots, sendCommand,
} from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { HealthPill, StatusBadge } from "@/components/StatusBadge";
import { useAuthStore } from "@/store/auth";
import { useToast } from "@/components/Toast";

export default function Robots() {
  const robots = useQuery({ queryKey: ["robots"], queryFn: listRobots });
  const fleet  = useQuery({ queryKey: ["fleet"],  queryFn: fleetSummary,
                            refetchInterval: 30_000 });
  const tel    = useQuery({ queryKey: ["telemetry", "latest_all"],
                            queryFn: latestTelemetryAll });
  const qc = useQueryClient();
  const toast = useToast();

  const canCommand = useAuthStore((s) =>
    s.user && ["admin", "engineer", "operator"].includes(s.user.role));

  const cmd = useMutation({
    mutationFn: (v: { id: string; command: string }) => sendCommand(v.id, v.command),
    onSuccess: (data: any, vars) => {
      toast.show({
        tone: data.delivered ? "success" : "warning",
        title: `${vars.command} → ${data.robot ?? vars.id.slice(0, 8)}`,
        body: data.delivered ? "Команду доставлено" : "MQTT недоступний",
      });
      qc.invalidateQueries({ queryKey: ["robots"] });
    },
    onError: (err: any, vars) => toast.show({
      tone: "error",
      title: "Помилка команди",
      body: err?.response?.data?.error?.detail ?? `Команда ${vars.command} не виконана`,
    }),
  });

  const healthByRobot = Object.fromEntries(
    (fleet.data ?? []).map((f) => [f.robot_id, f.health_score]),
  );
  const telByRobot = Object.fromEntries(
    (tel.data ?? []).map((t) => [t.robot_id, t]),
  );

  return (
    <div className="p-6">
      <PageHeader title="Флот роботів"
        subtitle="Перелік AMR з актуальним станом, останньою позицією та швидкими командами" />
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th className="p-3">Код</th>
              <th className="p-3">Модель</th>
              <th className="p-3">Статус</th>
              <th className="p-3">Зона</th>
              <th className="p-3">SoC</th>
              <th className="p-3">Здоров'я</th>
              <th className="p-3">Останній сигнал</th>
              {canCommand && <th className="p-3 text-right">Дії</th>}
            </tr>
          </thead>
          <tbody>
            {robots.isLoading && (
              <tr><td colSpan={canCommand ? 8 : 7} className="p-4 text-slate-500">
                Завантаження…
              </td></tr>
            )}
            {(robots.data ?? []).map((r) => {
              const t = telByRobot[r.id];
              const soc = t?.battery_soc;
              const health = healthByRobot[r.id];
              return (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="p-3 font-medium">
                    <Link className="text-brand-700 hover:underline" to={`/robots/${r.id}`}>
                      {r.code}
                    </Link>
                  </td>
                  <td className="p-3">{r.model}</td>
                  <td className="p-3"><StatusBadge status={r.status} /></td>
                  <td className="p-3">{r.last_zone ?? "—"}</td>
                  <td className="p-3">
                    {soc != null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1.5 bg-slate-100 rounded">
                          <div className={`h-full rounded ${
                            soc < 25 ? "bg-rose-500" :
                            soc < 50 ? "bg-amber-500" :
                                       "bg-emerald-500"}`}
                               style={{ width: `${Math.min(100, soc)}%` }} />
                        </div>
                        <span className="text-xs">{soc.toFixed(0)}%</span>
                      </div>
                    ) : "—"}
                  </td>
                  <td className="p-3">
                    {health != null ? <HealthPill score={health} /> : "—"}
                  </td>
                  <td className="p-3 text-slate-500 text-xs">
                    {r.last_seen_at
                      ? new Date(r.last_seen_at).toLocaleString()
                      : <span className="text-rose-500">offline</span>}
                  </td>
                  {canCommand && (
                    <td className="p-3 text-right">
                      <div className="inline-flex gap-1">
                        <button className="btn-secondary"
                                onClick={() => cmd.mutate({ id: r.id, command: "stop" })}>
                          Stop
                        </button>
                        <button className="btn-secondary"
                                onClick={() => cmd.mutate({ id: r.id, command: "resume" })}>
                          Resume
                        </button>
                        <button className="btn-secondary"
                                onClick={() => cmd.mutate({ id: r.id, command: "return_to_charge" })}>
                          Charge
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
            {!robots.isLoading && (robots.data ?? []).length === 0 && (
              <tr><td colSpan={canCommand ? 8 : 7} className="p-4 text-slate-500">
                Жодного робота в реєстрі. Відкрийте інтерфейс адміністратора, щоб додати.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

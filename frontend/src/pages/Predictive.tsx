import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fleetSummary, listRobots } from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { HealthPill } from "@/components/StatusBadge";

export default function Predictive() {
  const fleet = useQuery({ queryKey: ["fleet"], queryFn: fleetSummary, refetchInterval: 10000 });
  const robots = useQuery({ queryKey: ["robots"], queryFn: listRobots });

  return (
    <div className="p-6">
      <PageHeader title="Предиктивне обслуговування"
                  subtitle="Агрегований індекс здоров'я кожного робота за останнім вікном телеметрії" />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th className="p-3">Робот</th>
              <th className="p-3">Статус флоту</th>
              <th className="p-3">Індикатор</th>
              <th className="p-3">Дія</th>
            </tr>
          </thead>
          <tbody>
            {(fleet.data ?? []).map(f => {
              const robot = (robots.data ?? []).find(r => r.id === f.robot_id);
              const tone = f.health_score >= 85 ? "ok"
                         : f.health_score >= 65 ? "warn"
                         : "critical";
              return (
                <tr key={f.robot_id} className="border-t border-slate-100">
                  <td className="p-3">
                    <Link className="text-brand-600 hover:underline" to={`/robots/${f.robot_id}`}>{f.code}</Link>
                    {robot && <div className="text-xs text-slate-500">{robot.model}</div>}
                  </td>
                  <td className="p-3">
                    <div className="w-48 h-2 rounded bg-slate-100 overflow-hidden">
                      <div style={{ width: `${f.health_score}%` }}
                           className={
                             tone === "ok" ? "h-full bg-emerald-500"
                             : tone === "warn" ? "h-full bg-amber-500"
                             : "h-full bg-rose-500"
                           } />
                    </div>
                  </td>
                  <td className="p-3"><HealthPill score={f.health_score} /></td>
                  <td className="p-3">
                    <Link className="btn-secondary inline-flex" to={`/robots/${f.robot_id}`}>
                      Детально
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

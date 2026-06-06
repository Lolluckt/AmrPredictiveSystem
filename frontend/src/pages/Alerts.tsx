import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  listAnomalies, acknowledgeAnomaly, resolveAnomaly,
  listRules, createRule, updateRule, deleteRule,
  createTicketFromAnomaly,
} from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { SeverityBadge } from "@/components/StatusBadge";
import { useAuthStore } from "@/store/auth";
import { useToast } from "@/components/Toast";

export default function Alerts() {
  const role = useAuthStore(s => s.user?.role);
  const canManage = role === "admin" || role === "engineer";
  const toast = useToast();

  const anomalies = useQuery({
    queryKey: ["anomalies"],
    queryFn: () => listAnomalies({ unresolved: true }),
    refetchInterval: 30_000,
  });
  const rules = useQuery({ queryKey: ["rules"], queryFn: listRules });

  const qc = useQueryClient();
  const ack = useMutation({
    mutationFn: acknowledgeAnomaly,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["anomalies"] }),
  });
  const resolve = useMutation({
    mutationFn: resolveAnomaly,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["anomalies"] });
      toast.show({ tone: "success", title: "Аномалію закрито" });
    },
  });
  const removeRule = useMutation({
    mutationFn: deleteRule,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rules"] });
      toast.show({ tone: "success", title: "Правило видалено" });
    },
  });
  const toggleRule = useMutation({
    mutationFn: ({ id, rule }: { id: string; rule: any }) => updateRule(id, rule),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
  const makeTicket = useMutation({
    mutationFn: createTicketFromAnomaly,
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["anomalies"] });
      toast.show({
        tone: "success",
        title: "Заявку створено",
        body: `#${t.id.slice(0, 8)} · ${t.priority}`,
      });
    },
    onError: (err: any) => toast.show({
      tone: "error", title: "Не вдалося створити заявку",
      body: err?.response?.data?.error?.detail ?? "",
    }),
  });

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Сповіщення та правила"
                  subtitle="Активні аномалії та конфігурація порогів автоматичного виявлення" />

      <div className="card p-4">
        <div className="text-sm font-semibold mb-3">Відкриті аномалії</div>
        {anomalies.isLoading
          ? <div className="text-sm text-slate-500">Завантаження…</div>
          : (anomalies.data ?? []).length === 0
            ? <div className="text-sm text-slate-500">Порушень не зафіксовано.</div>
            : (
              <ul className="space-y-2">
                {anomalies.data!.map(a => (
                  <li key={a.id}
                      className="flex items-center gap-3 text-sm border-b border-slate-100 pb-2">
                    <SeverityBadge severity={a.severity} />
                    <div className="flex-1 min-w-0">
                      <div className="truncate">{a.message}</div>
                      <div className="text-xs text-slate-500">
                        {a.parameter} = {a.value} · поріг {a.threshold}
                        {" · "}{new Date(a.detected_at).toLocaleString()}
                        {a.acknowledged_at && (
                          <span className="text-emerald-600">
                            {" · підтвердив: "}
                            {a.acknowledged_by_name ?? "—"}
                            {" ("}{new Date(a.acknowledged_at).toLocaleTimeString()}{")"}
                          </span>
                        )}
                      </div>
                    </div>
                    {!a.acknowledged_at && (
                      <button className="btn-secondary"
                              onClick={() => ack.mutate(a.id)}>Підтвердити</button>
                    )}
                    {}
                    {a.acknowledged_at && (
                      <button className="btn-secondary"
                              disabled={makeTicket.isPending}
                              title={a.severity === "critical" || a.severity === "emergency"
                                ? "Для критичних заявку вже створено автоматично — відкриє наявну"
                                : "Створити заявку на ТО"}
                              onClick={() => makeTicket.mutate(a.id)}>
                        {makeTicket.isPending ? "..." : "Створити заявку"}
                      </button>
                    )}
                    <button className="btn-primary"
                            onClick={() => resolve.mutate(a.id)}>Закрити</button>
                  </li>
                ))}
              </ul>
            )
        }
      </div>

      {canManage && (
        <div className="card p-4">
          <div className="text-sm font-semibold mb-3">Правила сповіщень</div>
          <RulesForm onSaved={() => {
            qc.invalidateQueries({ queryKey: ["rules"] });
            toast.show({ tone: "success", title: "Правило додано" });
          }} />
          <table className="w-full text-sm mt-4">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left">Назва</th>
                <th className="text-left">Параметр</th>
                <th className="text-left">Умова</th>
                <th className="text-left">Режим</th>
                <th className="text-left">Серйозність</th>
                <th className="text-left">Увімк.</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(rules.data ?? []).map(r => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="py-2">{r.name}</td>
                  <td className="font-mono text-xs">{r.parameter}</td>
                  <td>{r.operator} {r.threshold}</td>
                  <td>
                    {r.mode === "adaptive"
                      ? <span className="text-xs text-violet-700">
                          μ±{r.k_sigma}σ ({r.window_minutes}хв)
                        </span>
                      : <span className="text-xs text-slate-500">static</span>}
                  </td>
                  <td><SeverityBadge severity={r.severity} /></td>
                  <td>
                    <input type="checkbox" checked={r.is_enabled}
                           onChange={(e) => toggleRule.mutate({
                             id: r.id,
                             rule: {
                               name: r.name, parameter: r.parameter, operator: r.operator,
                               threshold: r.threshold, severity: r.severity,
                               description: r.description, is_enabled: e.target.checked,
                               mode: r.mode ?? "static",
                               window_minutes: r.window_minutes ?? 30,
                               k_sigma: r.k_sigma ?? 3.0,
                             },
                           })} />
                  </td>
                  <td className="text-right">
                    <button className="btn-secondary"
                            onClick={() => {
                              if (confirm(`Видалити правило "${r.name}"?`))
                                removeRule.mutate(r.id);
                            }}>Видалити</button>
                  </td>
                </tr>
              ))}
              {(rules.data ?? []).length === 0 && (
                <tr><td colSpan={7} className="text-slate-500 py-3">Правил ще не створено.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RulesForm({ onSaved }: { onSaved: () => void }) {
  const [state, setState] = useState({
    name: "", parameter: "battery_temp", operator: ">", threshold: 50,
    severity: "warning", description: "", is_enabled: true,
    mode: "static" as "static" | "adaptive",
    window_minutes: 30, k_sigma: 3.0,
  });
  const toast = useToast();
  const create = useMutation({
    mutationFn: () => createRule(state as any),
    onSuccess: () => {
      setState({ ...state, name: "", description: "" });
      onSaved();
    },
    onError: (err: any) => toast.show({ tone: "error", title: "Не вдалося додати",
      body: err?.response?.data?.error?.detail ?? "" }),
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }}
          className="grid grid-cols-6 gap-2 items-end">
      <label className="text-xs col-span-2">
        Назва
        <input className="input" value={state.name} required minLength={3}
               onChange={e => setState({ ...state, name: e.target.value })} />
      </label>
      <label className="text-xs">
        Параметр
        <select className="input" value={state.parameter}
                onChange={e => setState({ ...state, parameter: e.target.value })}>
          <option value="battery_soc">battery_soc</option>
          <option value="battery_soh">battery_soh</option>
          <option value="battery_temp">battery_temp</option>
          <option value="battery_voltage">battery_voltage</option>
          <option value="left_motor_temp">left_motor_temp</option>
          <option value="right_motor_temp">right_motor_temp</option>
          <option value="left_motor_vib">left_motor_vib</option>
          <option value="right_motor_vib">right_motor_vib</option>
        </select>
      </label>
      <label className="text-xs">
        Умова
        <select className="input" value={state.operator}
                onChange={e => setState({ ...state, operator: e.target.value })}>
          {[">", ">=", "<", "<=", "==", "!="].map(o => <option key={o}>{o}</option>)}
        </select>
      </label>
      <label className="text-xs">
        Поріг
        <input type="number" step="0.1" className="input" value={state.threshold}
               onChange={e => setState({ ...state, threshold: Number(e.target.value) })} />
      </label>
      <label className="text-xs">
        Рівень
        <select className="input" value={state.severity}
                onChange={e => setState({ ...state, severity: e.target.value })}>
          {["info", "warning", "critical", "emergency"].map(s => <option key={s}>{s}</option>)}
        </select>
      </label>
      <label className="text-xs">
        Режим порога
        <select className="input" value={state.mode}
                onChange={e => setState({ ...state, mode: e.target.value as any })}
                title="static — постійний поріг; adaptive — поріг μ±k·σ з історії">
          <option value="static">static</option>
          <option value="adaptive">adaptive</option>
        </select>
      </label>
      {state.mode === "adaptive" && (
        <>
          <label className="text-xs">
            Вікно (хв)
            <input type="number" min={1} max={720} className="input"
                   value={state.window_minutes}
                   onChange={e => setState({ ...state, window_minutes: Number(e.target.value) })} />
          </label>
          <label className="text-xs">
            k·σ
            <input type="number" step="0.5" min={0.5} max={10} className="input"
                   value={state.k_sigma}
                   onChange={e => setState({ ...state, k_sigma: Number(e.target.value) })} />
          </label>
        </>
      )}
      <div className="col-span-6 flex justify-end">
        <button className="btn-primary" disabled={create.isPending}>
          {create.isPending ? "..." : "Додати правило"}
        </button>
      </div>
    </form>
  );
}


import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  cancelMission, createMission, listMissions, listRobots, listZones, updateMission,
} from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import type { Mission } from "@/types";

const STATUS_FILTERS = [
  "all", "queued", "assigned", "in_transit", "loading",
  "unloading", "completed", "failed", "cancelled",
];

export default function Missions() {
  const [statusFilter, setStatusFilter] = useState("all");
  const missions = useQuery({
    queryKey: ["missions", statusFilter],
    queryFn: () => listMissions(statusFilter === "all" ? {} : { status: statusFilter }),
  });
  const robots = useQuery({ queryKey: ["robots"], queryFn: listRobots });
  const zones  = useQuery({ queryKey: ["zones"],  queryFn: listZones });
  const qc = useQueryClient();
  const toast = useToast();

  const cancel = useMutation({
    mutationFn: cancelMission,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["missions"] });
      toast.show({ tone: "success", title: "Місію скасовано" });
    },
    onError: (err: any) => toast.show({ tone: "error", title: "Не вдалося скасувати",
      body: err?.response?.data?.error?.detail ?? "" }),
  });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Mission> }) =>
      updateMission(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["missions"] }),
    onError: (err: any) => toast.show({ tone: "error", title: "Не вдалося оновити",
      body: err?.response?.data?.error?.detail ?? "" }),
  });

  const [show, setShow] = useState(false);

  const robotName = (id?: string | null) =>
    id ? ((robots.data ?? []).find(r => r.id === id)?.code ?? id.slice(0, 8)) : "—";
  const zoneName = (id?: string | null) =>
    id ? ((zones.data ?? []).find(z => z.id === id)?.name ?? id.slice(0, 8)) : "—";

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Логістичні місії"
        subtitle="Поточні та заплановані транспортні завдання"
        actions={
          <div className="flex gap-2">
            <select className="input w-40" value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_FILTERS.map(s =>
                <option key={s} value={s}>{s === "all" ? "Усі статуси" : s}</option>)}
            </select>
            <button className="btn-primary" onClick={() => setShow(true)}>
              + Нова місія
            </button>
          </div>
        }
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th className="p-3">ID</th>
              <th className="p-3">Робот</th>
              <th className="p-3">Маршрут</th>
              <th className="p-3">Статус</th>
              <th className="p-3">Пріоритет</th>
              <th className="p-3">Вантаж</th>
              <th className="p-3">Створено</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {missions.isLoading && (
              <tr><td colSpan={8} className="p-4 text-slate-500">Завантаження…</td></tr>
            )}
            {(missions.data ?? []).map(m => (
              <tr key={m.id} className="border-t border-slate-100">
                <td className="p-3 font-mono text-xs">{m.id.slice(0, 8)}</td>
                <td className="p-3">{robotName(m.robot_id)}</td>
                <td className="p-3 text-xs">
                  <div>{zoneName(m.origin_zone_id)}</div>
                  <div className="text-slate-400">↓</div>
                  <div>{zoneName(m.destination_zone_id)}</div>
                </td>
                <td className="p-3"><StatusBadge status={m.status} /></td>
                <td className="p-3">
                  <select className="input w-28" value={m.priority}
                          disabled={["completed","cancelled","failed"].includes(m.status)}
                          onChange={(e) => update.mutate({
                            id: m.id, patch: { priority: e.target.value },
                          })}>
                    {["low", "medium", "high", "urgent"].map(p => <option key={p}>{p}</option>)}
                  </select>
                </td>
                <td className="p-3 text-xs">
                  {m.payload_type ?? "—"}
                  {m.payload_weight_kg ? <div className="text-slate-500">{m.payload_weight_kg} кг</div> : null}
                </td>
                <td className="p-3 text-slate-500 text-xs">
                  {new Date(m.created_at).toLocaleString()}
                </td>
                <td className="p-3 text-right">
                  {!["completed", "cancelled", "failed"].includes(m.status) && (
                    <button className="btn-secondary"
                            onClick={() => cancel.mutate(m.id)}>
                      Скасувати
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(missions.data ?? []).length === 0 && !missions.isLoading && (
              <tr><td colSpan={8} className="p-4 text-slate-500 text-center">
                Немає місій з обраним фільтром.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {show && (
        <CreateMissionModal
          robots={robots.data ?? []}
          zones={zones.data ?? []}
          onClose={() => setShow(false)}
          onCreated={() => {
            setShow(false);
            qc.invalidateQueries({ queryKey: ["missions"] });
            toast.show({ tone: "success", title: "Місію створено" });
          }}
        />
      )}
    </div>
  );
}

function CreateMissionModal({ robots, zones, onClose, onCreated }: {
  robots: { id: string; code: string }[];
  zones:  { id: string; name: string; zone_type: string }[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [state, setState] = useState({
    robot_id: "" as string,
    origin_zone_id:      zones[0]?.id ?? "",
    destination_zone_id: zones[1]?.id ?? "",
    payload_type: "raw_material",
    payload_weight_kg: 10,
    priority: "medium",
    notes: "",
  });
  const create = useMutation({
    mutationFn: () => createMission({
      ...state,
      robot_id: state.robot_id || undefined,
    } as any),
    onSuccess: onCreated,
    onError: (err: any) => toast.show({ tone: "error", title: "Помилка",
      body: err?.response?.data?.error?.detail ?? "Не вдалося створити" }),
  });

  return (
    <div className="fixed inset-0 bg-black/30 grid place-items-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5"
           onClick={(e) => e.stopPropagation()}>
        <div className="text-lg font-semibold mb-3">Нова логістична місія</div>
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-2">
          <label className="block text-xs">Робот (опціонально)
            <select className="input" value={state.robot_id}
                    onChange={(e) => setState({ ...state, robot_id: e.target.value })}>
              <option value="">— авто-призначення —</option>
              {robots.map(r => <option key={r.id} value={r.id}>{r.code}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-xs">Зона початку
              <select className="input" value={state.origin_zone_id}
                      onChange={(e) => setState({ ...state, origin_zone_id: e.target.value })}>
                {zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            </label>
            <label className="block text-xs">Зона призначення
              <select className="input" value={state.destination_zone_id}
                      onChange={(e) => setState({ ...state, destination_zone_id: e.target.value })}>
                {zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            </label>
          </div>
          <label className="block text-xs">Тип вантажу
            <select className="input" value={state.payload_type}
                    onChange={(e) => setState({ ...state, payload_type: e.target.value })}>
              {["raw_material", "semi_product", "finished_product", "tool", "empty"].map(t =>
                <option key={t}>{t}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-xs">Вага (кг)
              <input type="number" className="input" min={0} max={500}
                     value={state.payload_weight_kg}
                     onChange={(e) => setState({ ...state, payload_weight_kg: Number(e.target.value) })} />
            </label>
            <label className="block text-xs">Пріоритет
              <select className="input" value={state.priority}
                      onChange={(e) => setState({ ...state, priority: e.target.value })}>
                {["low", "medium", "high", "urgent"].map(p => <option key={p}>{p}</option>)}
              </select>
            </label>
          </div>
          <label className="block text-xs">Примітка
            <textarea className="input" value={state.notes}
                      onChange={(e) => setState({ ...state, notes: e.target.value })} />
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={onClose}>Скасувати</button>
            <button className="btn-primary" disabled={create.isPending}>
              {create.isPending ? "..." : "Створити"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  listRobots, listTickets, updateTicket, createTicket, addTicketComment,
} from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuthStore } from "@/store/auth";
import { useToast } from "@/components/Toast";
import type { Ticket } from "@/types";

const STATUSES: Ticket["status"][] = [
  "open", "assigned", "in_progress", "waiting_parts",
  "completed", "verified", "cancelled",
];

const COLUMN_TITLES: Record<string, string> = {
  open:           "Відкриті",
  assigned:       "Призначено",
  in_progress:    "Виконання",
  waiting_parts:  "Очікування ЗЧ",
  completed:      "Завершено",
  verified:       "Перевірено",
  cancelled:      "Скасовано",
};

const PRIORITY_TONE: Record<string, string> = {
  urgent: "bg-rose-100 text-rose-800 ring-rose-200",
  high:   "bg-amber-100 text-amber-800 ring-amber-200",
  medium: "bg-sky-100 text-sky-800 ring-sky-200",
  low:    "bg-slate-100 text-slate-700 ring-slate-200",
};

export default function Tickets() {
  const tickets = useQuery({ queryKey: ["tickets"], queryFn: () => listTickets() });
  const robots  = useQuery({ queryKey: ["robots"],  queryFn: listRobots });
  const qc = useQueryClient();
  const toast = useToast();
  const [selected, setSelected]     = useState<Ticket | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [filterRobot, setFilterRobot] = useState<string>("");

  const role = useAuthStore(s => s.user?.role);
  const canEdit = role === "admin" || role === "engineer";

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Ticket> }) =>
      updateTicket(id, patch),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      if (selected && selected.id === vars.id) {
        setSelected({ ...selected, ...vars.patch } as Ticket);
      }
    },
    onError: (err: any) =>
      toast.show({ tone: "error", title: "Не вдалося оновити заявку",
                   body: err?.response?.data?.error?.detail ?? "Спробуйте ще раз" }),
  });

  const grouped = useMemo(() => {
    const map: Record<string, Ticket[]> = {};
    STATUSES.forEach(s => (map[s] = []));
    (tickets.data ?? []).forEach(t => {
      if (filterRobot && t.robot_id !== filterRobot) return;
      const bucket = STATUSES.includes(t.status) ? t.status : "open";
      map[bucket].push(t);
    });
    return map;
  }, [tickets.data, filterRobot]);

  const robotName = (rid: string) =>
    (robots.data ?? []).find(r => r.id === rid)?.code ?? rid.slice(0, 8);

  function onDragStart(e: React.DragEvent, t: Ticket) {
    e.dataTransfer.setData("text/ticket-id", t.id);
    e.dataTransfer.setData("text/from-status", t.status);
    e.dataTransfer.effectAllowed = "move";
  }
  function onDrop(e: React.DragEvent, status: string) {
    e.preventDefault();
    const id   = e.dataTransfer.getData("text/ticket-id");
    const from = e.dataTransfer.getData("text/from-status");
    if (!id || from === status) return;
    if (!canEdit) {
      toast.show({ tone: "warning", title: "Недостатньо прав",
                   body: "Тільки інженер або адмін можуть змінювати статус." });
      return;
    }
    update.mutate({ id, patch: { status: status as Ticket["status"] } });
  }

  return (
    <div className="p-6">
      <PageHeader title="Заявки на обслуговування (CMMS)"
        subtitle="Канбан-дошка активних нарядів-допусків. Перетягніть картку для зміни статусу."
        actions={
          <div className="flex gap-2">
            <select className="input w-44" value={filterRobot}
                    onChange={(e) => setFilterRobot(e.target.value)}>
              <option value="">Всі роботи</option>
              {(robots.data ?? []).map(r =>
                <option key={r.id} value={r.id}>{r.code}</option>)}
            </select>
            <button className="btn-primary" onClick={() => setShowCreate(true)}>
              + Нова заявка
            </button>
          </div>
        }
      />

      <div className="grid gap-3 overflow-x-auto"
           style={{ gridTemplateColumns: "repeat(7, minmax(190px, 1fr))" }}>
        {STATUSES.map(col => (
          <div key={col}
               className="card p-3 min-h-[60vh]"
               onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}
               onDrop={(e) => onDrop(e, col)}>
            <div className="text-xs uppercase text-slate-500 mb-2 flex items-center justify-between">
              <span>{COLUMN_TITLES[col]}</span>
              <span className="badge-gray">{grouped[col].length}</span>
            </div>
            <div className="space-y-2">
              {grouped[col].map(t => (
                <div key={t.id}
                     draggable={canEdit}
                     onDragStart={(e) => onDragStart(e, t)}
                     onClick={() => setSelected(t)}
                     className={`border border-slate-200 rounded-md p-2 bg-white text-sm
                                 hover:shadow-sm transition cursor-pointer ${
                                 canEdit ? "active:opacity-70" : ""}`}>
                  <div className="font-medium line-clamp-2">{t.title}</div>
                  <div className="text-xs text-slate-500 mt-1 flex items-center justify-between">
                    <span>{robotName(t.robot_id)}</span>
                    <span className={`px-1.5 py-0.5 rounded ring-1 text-[10px] ${
                                PRIORITY_TONE[t.priority] ?? "bg-slate-100 ring-slate-200"}`}>
                      {t.priority}
                    </span>
                  </div>
                  {t.maintenance_type && (
                    <div className="text-[10px] text-slate-400 mt-1">{t.maintenance_type}</div>
                  )}
                </div>
              ))}
              {grouped[col].length === 0 && (
                <div className="text-[11px] text-slate-400 px-2 py-1">Пусто</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <Modal onClose={() => setSelected(null)}>
          <div className="flex items-start justify-between mb-2">
            <div>
              <div className="text-xs text-slate-500">Заявка</div>
              <div className="text-lg font-semibold">{selected.title}</div>
            </div>
            <StatusBadge status={selected.status} />
          </div>
          <div className="text-sm text-slate-700 whitespace-pre-wrap mb-3">
            {selected.description ?? "—"}
          </div>
          <div className="text-xs text-slate-500 space-y-0.5 mb-3">
            <div>Робот: {robotName(selected.robot_id)}</div>
            <div>Пріоритет: {selected.priority} · Тип: {selected.maintenance_type}</div>
            <div>Створено: {new Date(selected.created_at).toLocaleString()}</div>
          </div>
          {canEdit && (
            <div className="flex flex-wrap gap-2 mb-3">
              <select className="input w-auto" value={selected.status}
                onChange={(e) => update.mutate({ id: selected.id,
                                                 patch: { status: e.target.value as any } })}>
                {STATUSES.map(s => <option key={s} value={s}>{COLUMN_TITLES[s]}</option>)}
              </select>
              <select className="input w-auto" value={selected.priority}
                onChange={(e) => update.mutate({ id: selected.id,
                                                 patch: { priority: e.target.value } })}>
                {["low", "medium", "high", "urgent"].map(p => <option key={p}>{p}</option>)}
              </select>
            </div>
          )}
          <div className="text-xs uppercase text-slate-500 mb-1">Коментарі</div>
          <ul className="space-y-2 mb-2 max-h-48 overflow-y-auto">
            {(selected.comments ?? []).map(c => (
              <li key={c.id} className="text-sm border-l-2 border-brand-200 pl-2">
                {c.body}
                <div className="text-xs text-slate-400">
                  {new Date(c.created_at).toLocaleString()}
                </div>
              </li>
            ))}
            {(!selected.comments || selected.comments.length === 0) &&
              <li className="text-xs text-slate-500">Коментарів немає.</li>}
          </ul>
          <CommentForm ticketId={selected.id} onAdded={() => {
            qc.invalidateQueries({ queryKey: ["tickets"] });
          }} />
        </Modal>
      )}

      {showCreate && (
        <CreateTicketModal
          robots={robots.data ?? []}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            qc.invalidateQueries({ queryKey: ["tickets"] });
            toast.show({ tone: "success", title: "Заявку створено" });
          }}
        />
      )}
    </div>
  );
}

function CommentForm({ ticketId, onAdded }: { ticketId: string; onAdded: () => void }) {
  const [txt, setTxt] = useState("");
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => addTicketComment(ticketId, txt.trim()),
    onSuccess: () => { setTxt(""); onAdded(); },
    onError: (err: any) => toast.show({ tone: "error", title: "Не вдалося додати коментар",
                                        body: err?.response?.data?.error?.detail ?? "" }),
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (txt.trim()) m.mutate(); }}
          className="flex gap-2">
      <input className="input flex-1" placeholder="Додати коментар…"
             value={txt} onChange={(e) => setTxt(e.target.value)} />
      <button className="btn-primary" disabled={m.isPending || !txt.trim()}>
        {m.isPending ? "..." : "Надіслати"}
      </button>
    </form>
  );
}

function CreateTicketModal({ robots, onClose, onCreated }: {
  robots: { id: string; code: string }[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [state, setState] = useState({
    title: "", description: "",
    robot_id: robots[0]?.id ?? "",
    maintenance_type: "predictive",
    priority: "medium",
  });
  const create = useMutation({
    mutationFn: () => createTicket(state as any),
    onSuccess: onCreated,
    onError: (err: any) => toast.show({ tone: "error", title: "Помилка створення",
                                        body: err?.response?.data?.error?.detail ?? "" }),
  });
  return (
    <Modal onClose={onClose}>
      <div className="text-lg font-semibold mb-3">Нова заявка</div>
      <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-2">
        <label className="block text-xs">Робот
          <select className="input" value={state.robot_id}
                  onChange={(e) => setState({ ...state, robot_id: e.target.value })} required>
            {robots.map(r => <option key={r.id} value={r.id}>{r.code}</option>)}
          </select>
        </label>
        <label className="block text-xs">Тема
          <input className="input" value={state.title} required minLength={3}
                 onChange={(e) => setState({ ...state, title: e.target.value })} />
        </label>
        <label className="block text-xs">Опис
          <textarea className="input min-h-[90px]" value={state.description}
                    onChange={(e) => setState({ ...state, description: e.target.value })} />
        </label>
        <div className="flex gap-2">
          <label className="flex-1 text-xs">Тип
            <select className="input" value={state.maintenance_type}
                    onChange={(e) => setState({ ...state, maintenance_type: e.target.value })}>
              {["predictive", "preventive", "corrective", "emergency"].map(t =>
                <option key={t}>{t}</option>)}
            </select>
          </label>
          <label className="flex-1 text-xs">Пріоритет
            <select className="input" value={state.priority}
                    onChange={(e) => setState({ ...state, priority: e.target.value })}>
              {["low", "medium", "high", "urgent"].map(p => <option key={p}>{p}</option>)}
            </select>
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Скасувати</button>
          <button className="btn-primary" disabled={create.isPending}>
            {create.isPending ? "..." : "Створити"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Modal({ children, onClose }:
  { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/30 grid place-items-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-5"
           onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createUser, deleteUser, listUsers, updateUser } from "@/api/endpoints";
import { PageHeader } from "@/components/PageHeader";
import type { Role, User } from "@/types";

export default function Users() {
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const qc = useQueryClient();
  const [editing, setEditing] = useState<User | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const remove = useMutation({ mutationFn: deleteUser, onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }) });

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Користувачі" subtitle="Управління обліковими записами системи"
        actions={<button className="btn-primary" onClick={() => setShowCreate(true)}>+ Додати</button>} />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th className="p-3">Ім'я</th>
              <th className="p-3">Email</th>
              <th className="p-3">Роль</th>
              <th className="p-3">Посада</th>
              <th className="p-3">Активний</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {(users.data ?? []).map(u => (
              <tr key={u.id} className="border-t border-slate-100">
                <td className="p-3">{u.full_name}</td>
                <td className="p-3">{u.email}</td>
                <td className="p-3"><span className="badge-blue">{u.role}</span></td>
                <td className="p-3">{u.position_title ?? "—"}</td>
                <td className="p-3">{u.is_active ? "✅" : "⛔"}</td>
                <td className="p-3 flex justify-end gap-2">
                  <button className="btn-secondary" onClick={() => setEditing(u)}>Редагувати</button>
                  <button className="btn-danger"
                          onClick={() => { if (confirm(`Видалити ${u.email}?`)) remove.mutate(u.id); }}>
                    Видалити
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(showCreate || editing) && (
        <UserForm
          user={editing}
          onClose={() => { setEditing(null); setShowCreate(false); }}
          onSaved={() => { setEditing(null); setShowCreate(false); qc.invalidateQueries({ queryKey: ["users"] }); }}
        />
      )}
    </div>
  );
}

function UserForm({ user, onClose, onSaved }:
  { user: User | null; onClose: () => void; onSaved: () => void }) {
  const [state, setState] = useState({
    email: user?.email ?? "",
    full_name: user?.full_name ?? "",
    role: (user?.role ?? "operator") as Role,
    department: user?.department ?? "",
    position_title: user?.position_title ?? "",
    is_active: user?.is_active ?? true,
    password: "",
  });
  const save = useMutation({
    mutationFn: () =>
      user
        ? updateUser(user.id, { ...state, password: state.password || undefined } as any)
        : createUser(state as any),
    onSuccess: onSaved,
  });

  return (
    <div className="fixed inset-0 bg-black/30 grid place-items-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <div className="text-lg font-semibold mb-3">{user ? "Редагування користувача" : "Новий користувач"}</div>
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-2">
          <label className="block text-xs">Email
            <input className="input" type="email" value={state.email} required disabled={!!user}
                   onChange={(e) => setState({ ...state, email: e.target.value })} />
          </label>
          <label className="block text-xs">Повне ім'я
            <input className="input" value={state.full_name} required
                   onChange={(e) => setState({ ...state, full_name: e.target.value })} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-xs">Роль
              <select className="input" value={state.role}
                      onChange={(e) => setState({ ...state, role: e.target.value as Role })}>
                <option value="admin">admin</option>
                <option value="engineer">engineer</option>
                <option value="operator">operator</option>
              </select>
            </label>
            <label className="block text-xs">Відділ
              <input className="input" value={state.department}
                     onChange={(e) => setState({ ...state, department: e.target.value })} />
            </label>
          </div>
          <label className="block text-xs">Посада
            <input className="input" value={state.position_title}
                   onChange={(e) => setState({ ...state, position_title: e.target.value })} />
          </label>
          <label className="block text-xs">Пароль {user && <span className="text-slate-400">(залиште порожнім, щоб не змінювати)</span>}
            <input className="input" type="password" value={state.password} required={!user}
                   onChange={(e) => setState({ ...state, password: e.target.value })} />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={state.is_active}
                   onChange={(e) => setState({ ...state, is_active: e.target.checked })} />
            Активний
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={onClose}>Скасувати</button>
            <button className="btn-primary" disabled={save.isPending}>
              {user ? "Зберегти" : "Створити"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

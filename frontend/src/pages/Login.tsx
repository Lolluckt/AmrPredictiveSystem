import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, me } from "@/api/endpoints";
import { useAuthStore } from "@/store/auth";
import { Wrench } from "lucide-react";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@progress.ua");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const { access_token, refresh_token } = await login(email, password);
      useAuthStore.getState().setTokens(access_token, refresh_token);
      const user = await me();
      useAuthStore.getState().setUser(user);
      nav("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Помилка входу");
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-gradient-to-br from-brand-50 to-slate-100">
      <form onSubmit={submit} className="card w-full max-w-sm p-6">
        <div className="flex items-center gap-2 mb-4">
          <Wrench className="text-brand-600" />
          <div>
            <div className="text-lg font-semibold">AMR PdM</div>
            <div className="text-xs text-slate-500">Вхід у систему моніторингу</div>
          </div>
        </div>

        <label className="block text-sm font-medium mb-1">Email</label>
        <input className="input mb-3" value={email} onChange={(e) => setEmail(e.target.value)} />

        <label className="block text-sm font-medium mb-1">Пароль</label>
        <input type="password" className="input mb-3" value={password}
               onChange={(e) => setPassword(e.target.value)} />

        {error && <div className="badge-red mb-3 block p-2 text-xs">{error}</div>}

        <button className="btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Вхід..." : "Увійти"}
        </button>

        <div className="mt-4 border-t pt-3 text-xs text-slate-500 space-y-0.5">
          <div><b>Демо-акаунти:</b></div>
          <div>admin / engineer / operator @progress.ua</div>
          <div>паролі: admin123 · engineer123 · operator123</div>
        </div>
      </form>
    </div>
  );
}

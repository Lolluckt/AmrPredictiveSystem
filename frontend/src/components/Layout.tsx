import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/store/auth";
import {
  LayoutDashboard, Bot, Activity, AlertTriangle, TicketCheck,
  Truck, Users, LogOut, Wrench, BarChart3,
} from "lucide-react";
import { liveStatusEvent } from "./LiveChannelHost";
import type { LiveStatus } from "@/api/ws";

interface NavItem { to: string; label: string; icon: React.ReactNode; roles?: string[]; }

const NAV: NavItem[] = [
  { to: "/dashboard",  label: "Дашборд",           icon: <LayoutDashboard size={16} /> },
  { to: "/robots",     label: "Роботи",            icon: <Bot size={16} /> },
  { to: "/predictive", label: "Прогнозування",     icon: <Activity size={16} />, roles: ["admin","engineer"] },
  { to: "/analytics",  label: "Аналітика",         icon: <BarChart3 size={16} />, roles: ["admin","engineer"] },
  { to: "/alerts",     label: "Сповіщення",        icon: <AlertTriangle size={16} /> },
  { to: "/tickets",    label: "Заявки на ТО",      icon: <TicketCheck size={16} /> },
  { to: "/missions",   label: "Місії",             icon: <Truck size={16} /> },
  { to: "/admin/users",label: "Користувачі",       icon: <Users size={16} />, roles: ["admin"] },
];

function LiveStatusPill() {
  const [status, setStatus] = useState<LiveStatus>("idle");
  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<LiveStatus>;
      setStatus(ce.detail);
    };
    window.addEventListener(liveStatusEvent, handler);
    return () => window.removeEventListener(liveStatusEvent, handler);
  }, []);
  const tone =
    status === "open"       ? "bg-emerald-500" :
    status === "connecting" ? "bg-amber-500"   :
    status === "closed"     ? "bg-rose-500"    :
                              "bg-slate-300";
  const label =
    status === "open"       ? "Live" :
    status === "connecting" ? "Connecting…" :
    status === "closed"     ? "Offline" :
                              "Idle";
  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-600">
      <span className={cn("inline-block w-2 h-2 rounded-full", tone, status === "open" && "animate-pulse")} />
      {label}
    </div>
  );
}

export function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const nav = useNavigate();

  const items = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));

  return (
    <div className="flex h-screen bg-slate-50">
      <aside className="w-60 shrink-0 border-r border-slate-200 bg-white flex flex-col">
        <div className="px-4 py-4 border-b border-slate-200 flex items-center gap-2">
          <Wrench size={22} className="text-brand-600" />
          <div className="flex-1">
            <div className="text-sm font-semibold">AMR PdM</div>
            <div className="text-xs text-slate-500">Predictive Maintenance</div>
          </div>
        </div>
        <div className="px-4 py-2 border-b border-slate-200">
          <LiveStatusPill />
        </div>
        <nav className="flex-1 py-3 overflow-y-auto">
          {items.map((n) => (
            <NavLink
              key={n.to} to={n.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 px-4 py-2 text-sm",
                  isActive
                    ? "bg-brand-50 text-brand-700 border-l-2 border-brand-600"
                    : "text-slate-700 hover:bg-slate-50"
                )
              }
            >
              {n.icon}
              {n.label}
            </NavLink>
          ))}
        </nav>
        {user && (
          <div className="p-3 border-t border-slate-200">
            <div className="text-sm font-medium truncate">{user.full_name}</div>
            <div className="text-xs text-slate-500 truncate">{user.email}</div>
            <div className="text-xs mt-1">
              <span className="badge-blue">{user.role}</span>
            </div>
            <button
              className="btn-secondary w-full mt-2"
              onClick={() => { logout(); nav("/login"); }}
            >
              <LogOut size={14} /> Вийти
            </button>
          </div>
        )}
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}

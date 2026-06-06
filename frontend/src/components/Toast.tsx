
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from "react";
import { CheckCircle2, AlertTriangle, AlertOctagon, Info, X } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "success" | "error" | "warning" | "info";

interface ToastOpts {
  title: string;
  body?: string;
  tone?: Tone;
  durationMs?: number;
}

interface ToastItem extends Required<Omit<ToastOpts, "body">> {
  id: number;
  body?: string;
}

interface Ctx {
  show: (opts: ToastOpts) => void;
}

const ToastCtx = createContext<Ctx | null>(null);

export function useToast(): Ctx {
  const v = useContext(ToastCtx);
  if (!v) {

    return { show: () => undefined };
  }
  return v;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const show = useCallback((opts: ToastOpts) => {
    const id = ++idRef.current;
    const item: ToastItem = {
      id,
      title: opts.title,
      body: opts.body,
      tone: opts.tone ?? "info",
      durationMs: opts.durationMs ?? 4500,
    };
    setItems((prev) => [...prev, item]);
  }, []);

  useEffect(() => {
    if (!items.length) return;
    const timers = items.map((t) =>
      setTimeout(
        () => setItems((prev) => prev.filter((p) => p.id !== t.id)),
        t.durationMs,
      ),
    );
    return () => { timers.forEach(clearTimeout); };
  }, [items]);

  const value = useMemo<Ctx>(() => ({ show }), [show]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] space-y-2 w-80">
        {items.map((t) => <ToastCard key={t.id} item={t}
          onDismiss={() => setItems((prev) => prev.filter((p) => p.id !== t.id))}/>)}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const palette = {
    success: { bg: "bg-emerald-50 border-emerald-200", icon: <CheckCircle2 className="text-emerald-600" size={18} /> },
    info:    { bg: "bg-sky-50 border-sky-200",       icon: <Info        className="text-sky-600"     size={18} /> },
    warning: { bg: "bg-amber-50 border-amber-200",   icon: <AlertTriangle className="text-amber-600" size={18} /> },
    error:   { bg: "bg-rose-50 border-rose-200",     icon: <AlertOctagon  className="text-rose-600"  size={18} /> },
  }[item.tone];

  return (
    <div className={cn("rounded-lg border shadow-md p-3 flex gap-2 items-start", palette.bg)}>
      <div className="mt-0.5">{palette.icon}</div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{item.title}</div>
        {item.body && <div className="text-xs text-slate-600 mt-0.5 break-words">{item.body}</div>}
      </div>
      <button onClick={onDismiss} className="text-slate-400 hover:text-slate-600">
        <X size={16} />
      </button>
    </div>
  );
}

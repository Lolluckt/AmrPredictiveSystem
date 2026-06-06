
import { useEffect, useRef, useState } from "react";
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { useToast } from "@/components/Toast";

export type LiveStatus = "idle" | "connecting" | "open" | "closed";

export interface LiveEvent<T = any> {
  type: string;
  action?: string;
  id?: string | null;
  robot_id?: string | null;
  data?: T;
  ts?: string;
  history?: LiveEvent[];
  user?: { id: string; email: string; role: string };
}

function dispatch(qc: QueryClient, ev: LiveEvent, toast: ReturnType<typeof useToast>) {
  switch (ev.type) {
    case "telemetry": {
      const rid = ev.robot_id;
      if (rid) {
        qc.invalidateQueries({ queryKey: ["telemetry", "latest", rid] });
        qc.invalidateQueries({ queryKey: ["series", rid] });
      }

      qc.setQueryData<any[] | undefined>(["telemetry", "latest_all"], (prev) => {
        if (!prev || !ev.data) return prev;
        const idx = prev.findIndex((r) => r.robot_id === ev.data.robot_id);
        const next = [...prev];
        if (idx >= 0) next[idx] = { ...next[idx], ...ev.data };
        else          next.push(ev.data);
        return next;
      });
      qc.invalidateQueries({ queryKey: ["robots"] });
      break;
    }
    case "robot": {
      qc.invalidateQueries({ queryKey: ["robots"] });
      if (ev.id) qc.invalidateQueries({ queryKey: ["robot", ev.id] });
      if (ev.action === "command" && ev.data) {
        const ok = ev.data.delivered ? "✅" : "⚠️";
        toast.show({
          tone: ev.data.delivered ? "success" : "warning",
          title: `${ok} ${ev.data.robot_code} · ${ev.data.command}`,
          body:  ev.data.delivered
            ? "Команду доставлено в брокер MQTT."
            : "MQTT недоступний — команда не доставлена.",
        });
      }
      break;
    }
    case "anomaly": {
      qc.invalidateQueries({ queryKey: ["anomalies"] });
      qc.invalidateQueries({ queryKey: ["fleet"] });
      if (ev.action === "create" && ev.data) {
        toast.show({
          tone: ev.data.severity === "critical" || ev.data.severity === "emergency"
                  ? "error" : "warning",
          title: `Нова аномалія · ${ev.data.severity}`,
          body:  ev.data.message,
        });
      }
      break;
    }
    case "ticket": {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      if (ev.action === "create" && ev.data) {
        toast.show({ tone: "info", title: "Створено заявку", body: ev.data.title });
      }
      break;
    }
    case "mission": {
      qc.invalidateQueries({ queryKey: ["missions"] });
      break;
    }
    case "alert_rule": {
      qc.invalidateQueries({ queryKey: ["rules"] });
      break;
    }
    case "user": {
      qc.invalidateQueries({ queryKey: ["users"] });
      break;
    }
    default:
      break;
  }
}

export function useLiveChannel(): { status: LiveStatus; lastEvent: LiveEvent | null } {
  const qc = useQueryClient();
  const toast = useToast();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const closedByUs = useRef(false);
  const retryRef = useRef(0);

  useEffect(() => {
    if (!accessToken) {
      setStatus("idle");
      return;
    }
    closedByUs.current = false;

    function open() {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/api/ws?token=${encodeURIComponent(accessToken!)}`;
      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        retryRef.current = 0;
        setStatus("open");
      };
      ws.onmessage = (msg) => {
        try {
          const ev: LiveEvent = JSON.parse(msg.data);
          setLastEvent(ev);
          if (ev.type === "hello") {
            (ev.history ?? []).forEach((h) => dispatch(qc, h, toast));
            return;
          }
          if (ev.type === "ping") {
            try { ws.send("pong"); } catch {}
            return;
          }
          dispatch(qc, ev, toast);
        } catch {

        }
      };
      ws.onclose = () => {
        setStatus("closed");
        if (closedByUs.current) return;
        const delay = Math.min(15000, 1000 * Math.pow(2, retryRef.current++));
        setTimeout(open, delay);
      };
      ws.onerror = () => { try { ws.close(); } catch {} };
    }

    open();
    return () => {
      closedByUs.current = true;
      try { wsRef.current?.close(); } catch {}
    };
  }, [accessToken, qc, toast]);

  return { status, lastEvent };
}

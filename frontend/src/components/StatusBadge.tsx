import { cn } from "@/lib/cn";

const STATUS_TONE: Record<string, string> = {
  operational: "badge-green",
  idle: "badge-gray",
  charging: "badge-blue",
  warning: "badge-yellow",
  critical: "badge-red",
  completed: "badge-green",
  verified: "badge-green",
  in_progress: "badge-blue",
  assigned: "badge-blue",
  open: "badge-yellow",
  waiting_parts: "badge-yellow",
  cancelled: "badge-gray",
  queued: "badge-gray",
  in_transit: "badge-blue",
  loading: "badge-blue",
  unloading: "badge-blue",
  failed: "badge-red",
};

const STATUS_LABEL: Record<string, string> = {
  operational: "В роботі",
  idle: "Очікує",
  charging: "Зарядка",
  warning: "Попередження",
  critical: "Критичний",
  open: "Відкрита",
  assigned: "Призначена",
  in_progress: "Виконується",
  waiting_parts: "Очікує ЗЧ",
  completed: "Завершена",
  verified: "Перевірена",
  cancelled: "Скасована",
  queued: "У черзі",
  in_transit: "В дорозі",
  loading: "Завантаження",
  unloading: "Розвантаження",
  failed: "Невдала",
};

export function StatusBadge({ status }: { status: string }) {
  const classes = STATUS_TONE[status] ?? "badge-gray";
  const label = STATUS_LABEL[status] ?? status;
  return <span className={cn(classes)} title={status}>{label}</span>;
}

const SEVERITY_LABEL: Record<string, string> = {
  info: "Інформація",
  warning: "Попередження",
  critical: "Критична",
  emergency: "Аварійна",
};

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: Record<string, string> = {
    info: "badge-blue",
    warning: "badge-yellow",
    critical: "badge-red",
    emergency: "badge-red",
  };
  return <span className={tone[severity] ?? "badge-gray"} title={severity}>
    {SEVERITY_LABEL[severity] ?? severity}
  </span>;
}

export function HealthPill({ score }: { score: number }) {
  const tone =
    score >= 85 ? "badge-green" :
    score >= 65 ? "badge-yellow" :
    "badge-red";
  return <span className={tone}>{score.toFixed(0)}%</span>;
}


import { useMemo } from "react";
import type { FactoryLayout, Robot, Telemetry } from "@/types";

interface Props {
  layout?: FactoryLayout;
  robots: Robot[];
  telemetry: Telemetry[];
  selectedRobotId?: string | null;
  onSelectRobot?: (id: string) => void;
  height?: number;
}

const STATUS_COLOR: Record<string, string> = {
  operational: "#10b981",
  idle:        "#94a3b8",
  charging:    "#3b82f6",
  warning:     "#f59e0b",
  critical:    "#ef4444",
};

export function FactoryMap({
  layout, robots, telemetry, selectedRobotId, onSelectRobot, height = 360,
}: Props) {
  const { vbX, vbY, vbW, vbH } = useMemo(() => {
    const zs = layout?.zones ?? [];
    if (!zs.length) return { vbX: 0, vbY: 0, vbW: 40, vbH: 24 };
    const minX = Math.min(...zs.map(z => z.x_min));
    const minY = Math.min(...zs.map(z => z.y_min));
    const maxX = Math.max(...zs.map(z => z.x_max));
    const maxY = Math.max(...zs.map(z => z.y_max));
    return { vbX: minX - 1, vbY: minY - 1,
             vbW: (maxX - minX) + 2, vbH: (maxY - minY) + 2 };
  }, [layout]);

  const telByRobot = useMemo(() => {
    const m = new Map<string, Telemetry>();
    telemetry.forEach(t => m.set(t.robot_id, t));
    return m;
  }, [telemetry]);

  const robotPos = (r: Robot) => {
    const t = telByRobot.get(r.id);
    const x = t?.pos_x ?? r.last_x;
    const y = t?.pos_y ?? r.last_y;
    return (x != null && y != null) ? { x, y } : null;
  };

  return (
    <div className="card p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold">Карта цеху · Живі позиції AMR</div>
        <div className="flex flex-wrap gap-2 text-[11px] text-slate-500">
          {Object.entries(STATUS_COLOR).map(([k, c]) => (
            <span key={k} className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: c }} />{k}
            </span>
          ))}
        </div>
      </div>
      <svg viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
           preserveAspectRatio="xMidYMid meet"
           style={{ width: "100%", height }}
           className="bg-slate-50 rounded-md border border-slate-200">
        {}
        <defs>
          <pattern id="grid" width="2" height="2" patternUnits="userSpaceOnUse">
            <path d="M 2 0 L 0 0 0 2" fill="none" stroke="#e2e8f0" strokeWidth="0.05"/>
          </pattern>
        </defs>
        <rect x={vbX} y={vbY} width={vbW} height={vbH} fill="url(#grid)" />

        {(layout?.zones ?? []).map(z => (
          <g key={z.id}>
            <rect
              x={z.x_min} y={z.y_min}
              width={z.x_max - z.x_min} height={z.y_max - z.y_min}
              fill={z.color_hex} fillOpacity={0.18}
              stroke={z.color_hex} strokeOpacity={0.6} strokeWidth={0.05}
            />
            <text
              x={(z.x_min + z.x_max) / 2}
              y={(z.y_min + z.y_max) / 2}
              fontSize={0.6}
              textAnchor="middle"
              fill="#475569"
              style={{ pointerEvents: "none" }}
            >
              {z.name}
            </text>
          </g>
        ))}

        {(layout?.chargers ?? []).map(c => (
          <g key={c.id}>
            <rect x={c.x_position - 0.4} y={c.y_position - 0.4}
                  width={0.8} height={0.8}
                  fill={c.is_occupied ? "#3b82f6" : "#cbd5e1"}
                  stroke="#1e3a8a" strokeWidth={0.05} rx={0.1} />
            <text x={c.x_position} y={c.y_position - 0.6}
                  fontSize={0.4} textAnchor="middle" fill="#1e3a8a">{c.code}</text>
          </g>
        ))}

        {robots.map(r => {
          const pos = robotPos(r);
          if (!pos) return null;
          const colour = STATUS_COLOR[r.status] ?? "#64748b";
          const selected = selectedRobotId === r.id;
          return (
            <g key={r.id}
               style={{ cursor: onSelectRobot ? "pointer" : "default" }}
               onClick={() => onSelectRobot?.(r.id)}>
              <circle cx={pos.x} cy={pos.y} r={selected ? 0.7 : 0.55}
                      fill={colour} stroke="#fff" strokeWidth={0.1} />
              <circle cx={pos.x} cy={pos.y} r={selected ? 1.2 : 0.9}
                      fill={colour} fillOpacity={0.18} />
              <text x={pos.x} y={pos.y - 1.0} fontSize={0.55}
                    textAnchor="middle" fill="#0f172a">{r.code}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

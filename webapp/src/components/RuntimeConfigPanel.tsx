import { Settings } from "lucide-react";
import type { RuntimeConfig } from "../types/domain";

interface Props {
  config: RuntimeConfig;
  onChange: (config: RuntimeConfig) => void;
  onApply: () => void;
  disabled: boolean;
}

function NumericInput({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-black/20 p-3">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">{label}</div>
      <div className="flex items-center gap-3">
        <button
          className="h-8 w-8 rounded-lg border border-slate-700 bg-slate-900 text-slate-200"
          onClick={() => onChange(Number((value - step).toFixed(3)))}
          type="button"
        >
          -
        </button>
        <input
          className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-center text-sm font-bold text-cyan-200"
          type="number"
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        <button
          className="h-8 w-8 rounded-lg border border-slate-700 bg-slate-900 text-slate-200"
          onClick={() => onChange(Number((value + step).toFixed(3)))}
          type="button"
        >
          +
        </button>
      </div>
    </div>
  );
}

export function RuntimeConfigPanel({ config, onChange, onApply, disabled }: Props) {
  const updateOffset = (index: 0 | 1 | 2, value: number) => {
    const next = [...config.base_offset_m] as [number, number, number];
    next[index] = value;
    onChange({ ...config, base_offset_m: next });
  };

  const updateRpy = (index: 0 | 1 | 2, value: number) => {
    const next = [...config.pose_rpy_deg] as [number, number, number];
    next[index] = value;
    onChange({ ...config, pose_rpy_deg: next });
  };

  return (
    <section className="hud-panel rounded-[28px] p-5">
      <div className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.28em] text-amber-300">
        <Settings size={14} />
        Runtime Config
      </div>

      <div className="space-y-3">
        <NumericInput label="Hover Height (m)" value={config.hover_height_m} step={0.01} onChange={(value) => onChange({ ...config, hover_height_m: value })} />
        <NumericInput label="Grasp Offset (m)" value={config.grasp_z_offset_m} step={0.01} onChange={(value) => onChange({ ...config, grasp_z_offset_m: value })} />
        <NumericInput label="Drop Hover Z (m)" value={config.drop_hover_z_m} step={0.01} onChange={(value) => onChange({ ...config, drop_hover_z_m: value })} />
        <NumericInput label="Drop Z (m)" value={config.drop_z_m} step={0.01} onChange={(value) => onChange({ ...config, drop_z_m: value })} />
        <NumericInput label="Follow Rate (Hz)" value={config.follow_rate_hz} step={1} onChange={(value) => onChange({ ...config, follow_rate_hz: value })} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <NumericInput label="Offset X" value={config.base_offset_m[0]} step={0.01} onChange={(value) => updateOffset(0, value)} />
        <NumericInput label="Offset Y" value={config.base_offset_m[1]} step={0.01} onChange={(value) => updateOffset(1, value)} />
        <NumericInput label="Offset Z" value={config.base_offset_m[2]} step={0.01} onChange={(value) => updateOffset(2, value)} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <NumericInput label="Pose RX" value={config.pose_rpy_deg[0]} step={1} onChange={(value) => updateRpy(0, value)} />
        <NumericInput label="Pose RY" value={config.pose_rpy_deg[1]} step={1} onChange={(value) => updateRpy(1, value)} />
        <NumericInput label="Pose RZ" value={config.pose_rpy_deg[2]} step={1} onChange={(value) => updateRpy(2, value)} />
      </div>

      <div className="mt-4 rounded-2xl border border-slate-800 bg-black/20 p-3">
        <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">Target Labels</div>
        <div className="flex flex-wrap gap-2">
          {["bottle", "cup"].map((label) => {
            const active = config.target_labels.includes(label);
            return (
              <button
                key={label}
                type="button"
                onClick={() => {
                  const next = active
                    ? config.target_labels.filter((item) => item !== label)
                    : [...config.target_labels, label];
                  onChange({ ...config, target_labels: next });
                }}
                className={[
                  "rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.22em]",
                  active ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-200" : "border-slate-700 bg-slate-900 text-slate-400",
                ].join(" ")}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <button
        onClick={onApply}
        disabled={disabled}
        className={[
          "mt-5 w-full rounded-2xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-xs font-black uppercase tracking-[0.28em] text-cyan-100 transition",
          disabled ? "cursor-not-allowed opacity-30 grayscale" : "hover:bg-cyan-500/15 shadow-glowCyan",
        ].join(" ")}
      >
        Apply to Backend
      </button>
    </section>
  );
}

import { Activity, Binary, Cpu, ShieldCheck } from "lucide-react";
import type { SystemStatus } from "../types/domain";

function StatusChip({ label, active }: { label: string; active: boolean }) {
  return (
    <div
      className={[
        "flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-bold tracking-[0.2em]",
        active
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 shadow-glowEmerald"
          : "border-rose-500/30 bg-rose-500/10 text-rose-300",
      ].join(" ")}
    >
      <span className={["h-2 w-2 rounded-full", active ? "bg-emerald-400 animate-pulse" : "bg-rose-400"].join(" ")} />
      {label}
    </div>
  );
}

export function StatusBar({ status, isMock }: { status: SystemStatus | null; isMock: boolean }) {
  return (
    <header className="hud-panel hud-grid rounded-[28px] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-cyan-500/20 bg-cyan-500/10 shadow-glowCyan">
            <Cpu className="text-cyan-400" size={28} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-black tracking-tight text-white">NERO FAKE_GRASP CONSOLE</h1>
              {isMock ? (
                <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-[10px] font-black tracking-[0.25em] text-amber-300">
                  MOCK MODE
                </span>
              ) : null}
            </div>
            <p className="mt-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.3em] text-slate-500">
              <Binary size={12} />
              本地现场操作台 / Fake Grasp Workflow
            </p>
          </div>
        </div>

        <div className="flex flex-col items-start gap-3 lg:items-end">
          <div className="flex flex-wrap gap-2">
            <StatusChip label="CAN0" active={Boolean(status?.can_up)} />
            <StatusChip label="ROBOT" active={Boolean(status?.robot_connected)} />
            <StatusChip label="CAMERA" active={Boolean(status?.camera_ready)} />
            <StatusChip label="YOLO" active={Boolean(status?.model_ready)} />
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 font-semibold text-cyan-200">
              calibration: {status?.calibration_file ? status.calibration_file.split("/").pop() : "loading"}
            </span>
            <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1 font-semibold uppercase text-amber-200">
              <Activity className="mr-2 inline-block" size={12} />
              {status?.current_mode ?? "loading"}
            </span>
            <span className="rounded-full border border-slate-700 bg-black/20 px-3 py-1 font-semibold text-slate-300">
              busy: {status?.busy ? "yes" : "no"}
            </span>
            <span className="rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1 font-semibold text-rose-200">
              <ShieldCheck className="mr-2 inline-block" size={12} />
              min z {status?.safety.min_z_m?.toFixed(2) ?? "0.10"}m
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}

import { Crosshair, Database, Target } from "lucide-react";
import type { DetectionState } from "../types/domain";

function formatVec(values?: number[]) {
  if (!values?.length) return "n/a";
  return values.map((value) => value.toFixed(3)).join(", ");
}

export function DetectionCard({ detection }: { detection: DetectionState | null }) {
  const target = detection?.target;

  return (
    <section className="hud-panel rounded-[28px] p-5">
      <div className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.28em] text-cyan-300">
        <Database size={14} />
        Detection Meta
      </div>
      {target ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <div className="rounded-2xl border border-slate-800 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Class</div>
              <div className="mt-2 text-sm font-black text-white">{target.class_name}</div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Target</div>
              <div className="mt-2 text-sm font-black text-cyan-300">{target.target_name}</div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Confidence</div>
              <div className="mt-2 text-sm font-black text-emerald-300">{(target.confidence * 100).toFixed(1)}%</div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Top-K</div>
              <div className="mt-2 text-sm font-black text-amber-300">{detection?.top_detections?.length ?? 0}</div>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            <div className="rounded-2xl border border-slate-800 bg-black/20 p-4">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">
                <Crosshair size={13} />
                Camera XYZ
              </div>
              <div className="font-mono text-sm text-cyan-200">{formatVec(target.camera_xyz_m)}</div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-black/20 p-4">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">
                <Target size={13} />
                Base XYZ
              </div>
              <div className="font-mono text-sm text-emerald-200">{formatVec(target.base_xyz_m)}</div>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <PosePreview label="Hover" pose={target.hover_pose} />
            <PosePreview label="Pregrasp" pose={target.pregrasp_pose} />
            <PosePreview label="Drop Hover" pose={target.drop_hover_pose} />
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-800 bg-black/20 p-6 text-sm text-slate-500">
          当前没有有效目标。请确认相机、YOLO 和检测目标是否正常。
        </div>
      )}
    </section>
  );
}

function PosePreview({ label, pose }: { label: string; pose?: [number, number, number, number, number, number] }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-black/20 p-4">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">{label}</div>
      <div className="font-mono text-xs text-slate-300">{pose ? pose.map((value) => value.toFixed(3)).join(", ") : "n/a"}</div>
    </div>
  );
}

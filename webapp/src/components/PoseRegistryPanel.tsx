import { Database, Save } from "lucide-react";
import type { DropPosesResponse, TaskPosesResponse } from "../types/domain";

interface Props {
  taskPoses: TaskPosesResponse | null;
  dropPoses: DropPosesResponse | null;
  onRecordTask: (name: "home" | "work" | "standby") => void;
  onRecordDrop: (name: "bottle" | "cup") => void;
}

function RegistryButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-black/20 px-4 py-3 text-xs font-bold uppercase tracking-[0.24em] text-slate-300 transition hover:border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-200"
    >
      <span>{label}</span>
      <Save size={14} />
    </button>
  );
}

export function PoseRegistryPanel({ taskPoses, dropPoses, onRecordTask, onRecordDrop }: Props) {
  return (
    <section className="hud-panel rounded-[28px] p-5">
      <div className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.28em] text-emerald-300">
        <Database size={14} />
        YAML Registry
      </div>

      <div className="space-y-3">
        <div className="rounded-2xl border border-slate-800 bg-black/20 p-4">
          <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">Task Poses (6D)</div>
          <div className="space-y-2">
            <RegistryButton label={`Record Home${taskPoses?.task_poses.home ? " (override)" : ""}`} onClick={() => onRecordTask("home")} />
            <RegistryButton label={`Record Work${taskPoses?.task_poses.work ? " (override)" : ""}`} onClick={() => onRecordTask("work")} />
            <RegistryButton label={`Record Standby${taskPoses?.task_poses.standby ? " (override)" : ""}`} onClick={() => onRecordTask("standby")} />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-black/20 p-4">
          <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">Drop Centers (XY)</div>
          <div className="space-y-2">
            <RegistryButton label={`Record Bottle Drop${dropPoses?.drop_poses.bottle ? " (override)" : ""}`} onClick={() => onRecordDrop("bottle")} />
            <RegistryButton label={`Record Cup Drop${dropPoses?.drop_poses.cup ? " (override)" : ""}`} onClick={() => onRecordDrop("cup")} />
          </div>
        </div>
      </div>
    </section>
  );
}

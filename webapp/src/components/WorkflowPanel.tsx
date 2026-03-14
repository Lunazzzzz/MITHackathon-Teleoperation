import type { ReactNode } from "react";
import { Play, Route, Square, Waves } from "lucide-react";
import { WORKFLOW_STEPS } from "../features/workflow/workflowSteps";
import type { WorkflowStep } from "../types/domain";

interface WorkflowPanelProps {
  currentStep?: WorkflowStep | null;
  canRunFakeGrasp: boolean;
  canStartFollow: boolean;
  busy: boolean;
  onMoveHome: () => void;
  onMoveWork: () => void;
  onMoveStandby: () => void;
  onRunFakeGrasp: () => void;
  onStartFollow: () => void;
  onStopFollow: () => void;
  onStopTask: () => void;
}

function ActionButton({
  label,
  onClick,
  disabled,
  tone = "default",
  icon,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  tone?: "default" | "primary" | "danger";
  icon: ReactNode;
}) {
  const toneClass =
    tone === "primary"
      ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/15"
      : tone === "danger"
        ? "border-rose-500/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/15"
        : "border-slate-700 bg-black/20 text-slate-200 hover:bg-slate-800/70";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={[
        "flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-xs font-black uppercase tracking-[0.25em] transition",
        toneClass,
        disabled ? "cursor-not-allowed opacity-30 grayscale" : "",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}

export function WorkflowPanel(props: WorkflowPanelProps) {
  return (
    <section className="hud-panel rounded-[28px] p-5">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.28em] text-cyan-300">
          <Route size={14} />
          Process Logic
        </div>
        <ActionButton label="Stop Task" onClick={props.onStopTask} disabled={false} tone="danger" icon={<Square size={14} />} />
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <ActionButton label="Home" onClick={props.onMoveHome} disabled={props.busy} icon={<Route size={14} />} />
        <ActionButton label="Work" onClick={props.onMoveWork} disabled={props.busy} icon={<Route size={14} />} />
        <ActionButton label="Standby" onClick={props.onMoveStandby} disabled={props.busy} icon={<Route size={14} />} />
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <ActionButton
          label="Run Fake Grasp"
          onClick={props.onRunFakeGrasp}
          disabled={!props.canRunFakeGrasp}
          tone="primary"
          icon={<Play size={14} />}
        />
        <div className="grid grid-cols-2 gap-3">
          <ActionButton
            label="Start Follow"
            onClick={props.onStartFollow}
            disabled={!props.canStartFollow}
            icon={<Waves size={14} />}
          />
          <ActionButton label="Stop Follow" onClick={props.onStopFollow} disabled={false} icon={<Square size={14} />} />
        </div>
      </div>

      <div className="space-y-2 rounded-[24px] border border-slate-800 bg-black/20 p-4">
        {WORKFLOW_STEPS.map((step, index) => {
          const active = props.currentStep === step;
          return (
            <div
              key={step}
              className={[
                "flex items-center gap-4 rounded-2xl border px-4 py-3 transition",
                active ? "translate-x-1 border-cyan-500/30 bg-cyan-500/10 shadow-glowCyan" : "border-transparent text-slate-500",
              ].join(" ")}
            >
              <div
                className={[
                  "flex h-8 w-8 items-center justify-center rounded-xl border text-[11px] font-black",
                  active ? "border-cyan-400 bg-cyan-500 text-slate-950" : "border-slate-700 bg-slate-900 text-slate-600",
                ].join(" ")}
              >
                {(index + 1).toString().padStart(2, "0")}
              </div>
              <span className={["text-xs font-black uppercase tracking-[0.24em]", active ? "text-cyan-200" : ""].join(" ")}>
                {step}
              </span>
              {active ? <span className="ml-auto h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" /> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

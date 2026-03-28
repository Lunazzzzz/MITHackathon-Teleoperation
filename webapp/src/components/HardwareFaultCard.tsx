import { Terminal, WifiOff } from "lucide-react";

export function HardwareFaultCard() {
  return (
    <div className="rounded-[24px] border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
      <div className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-[0.28em] text-rose-300">
        <WifiOff size={14} />
        CAN0 Offline
      </div>
      <p className="mb-3 leading-6 text-rose-100/90">
        检测到 CAN 接口未处于可用状态。机械臂运动按钮已禁用，请先在终端恢复 `can0`。
      </p>
      <div className="rounded-2xl border border-slate-800 bg-black/30 p-3 font-mono text-xs text-slate-200">
        <div>cd /home/robot/project/sort_trash/pyAgxArm/pyAgxArm/scripts/ubuntu</div>
        <div className="mt-1">sudo bash can_activate.sh can0 1000000</div>
      </div>
      <div className="mt-3 flex items-center gap-2 text-xs text-rose-200/80">
        <Terminal size={12} />
        执行完成后刷新页面或等待状态轮询恢复。
      </div>
    </div>
  );
}

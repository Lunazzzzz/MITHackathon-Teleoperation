import { AlertTriangle, ShieldAlert } from "lucide-react";

export function SafetyAlert({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-[24px] border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
      <div className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-[0.28em] text-amber-300">
        <ShieldAlert size={14} />
        {title}
      </div>
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 shrink-0 text-amber-300" size={18} />
        <p className="leading-6 text-amber-100/90">{message}</p>
      </div>
    </div>
  );
}

import { Camera, ScanSearch } from "lucide-react";
import { isMockMode } from "../api/client";
import { MOCK_VIDEO_PLACEHOLDER } from "../mocks/fixtures";

export function VideoPanel() {
  const src = isMockMode() ? MOCK_VIDEO_PLACEHOLDER : "/api/video.mjpg";

  return (
    <section className="hud-panel relative overflow-hidden rounded-[28px] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.28em] text-cyan-300">
          <Camera size={14} />
          Live Vision Feed
        </div>
        <div className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.25em] text-cyan-200">
          MJPEG
        </div>
      </div>
      <div className="relative aspect-video overflow-hidden rounded-2xl border border-slate-800 bg-black">
        <img
          src={src}
          alt="Video stream"
          className="h-full w-full object-contain"
          onError={(event) => {
            const target = event.currentTarget;
            target.src = MOCK_VIDEO_PLACEHOLDER;
          }}
        />
        <div className="pointer-events-none absolute inset-0 border-[16px] border-transparent border-t-slate-950/20 border-l-slate-950/20" />
        <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-full border border-rose-500/30 bg-black/40 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.25em] text-rose-200 backdrop-blur">
          <span className="h-2 w-2 rounded-full bg-rose-400 animate-pulse" />
          D435 stream active
        </div>
        <div className="pointer-events-none absolute bottom-4 right-4 rounded-full border border-slate-700 bg-black/40 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.25em] text-slate-300 backdrop-blur">
          <ScanSearch className="mr-2 inline-block" size={12} />
          Targeting HUD
        </div>
      </div>
    </section>
  );
}

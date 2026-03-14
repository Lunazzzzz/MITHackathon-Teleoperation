import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        hud: {
          bg: "#020617",
          panel: "#0f172a",
          panelAlt: "#111c33",
          cyan: "#06b6d4",
          emerald: "#10b981",
          amber: "#f59e0b",
          rose: "#f43f5e"
        }
      },
      boxShadow: {
        glowCyan: "0 0 24px rgba(6, 182, 212, 0.18)",
        glowEmerald: "0 0 24px rgba(16, 185, 129, 0.18)",
        glowRose: "0 0 24px rgba(244, 63, 94, 0.18)"
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.06) 1px, transparent 1px)"
      }
    }
  },
  plugins: []
} satisfies Config;

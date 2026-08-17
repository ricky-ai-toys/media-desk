const MOM_LVL: Record<string, number> = {
  accelerating: 4, hot: 4, rising: 3, stable: 2, shifting: 2,
  emerging: 3, new: 3, fading: 1, cold: 1,
};

export const MOM_ARROW: Record<string, string> = {
  accelerating: "↗", rising: "↑", stable: "→", fading: "↘", new: "↖", emerging: "↖",
};

/** Tiny ticker sparkline; one trend, five samples, currentColor. */
export function sparkSvg(momentum?: string | null): string {
  const v = MOM_LVL[String(momentum || "").toLowerCase()] || 2;
  const pts = [
    v === 4 ? 2 : v === 3 ? 5 : v === 1 ? 14 : 10,
    v === 4 ? 14 : v === 3 ? 11 : v === 1 ? 5 : 8,
    v === 4 ? 10 : v === 3 ? 9 : v === 1 ? 10 : 9,
    v === 4 ? 6 : v === 3 ? 7 : v === 1 ? 12 : 8,
  ];
  return `<svg class="spark" viewBox="0 0 36 12" aria-hidden="true">
    <polyline fill="none" stroke="currentColor" stroke-width="1.4" points="${pts.map((y, i) => i * 9 + "," + y).join(" ")}"/>
    <polygon points="32,${pts[3]} 32,12 0,12" fill="currentColor" fill-opacity=".07"/>
  </svg>`;
}

/** Narrative shift arrow: from-box -> dashed line -> to-box. */
export function shiftSvg(from: string, to: string, cls = ""): string {
  return `<svg class="shift-viz ${cls}" viewBox="0 0 120 18" aria-hidden="true">
    <rect x="0" y="3" width="16" height="7" rx="1" class="s-from"/>
    <line x1="16" y1="6" x2="104" y2="6" class="s-line" stroke-dasharray="2 2"/>
    <polygon points="104,3 104,9 112,6" class="s-head"/>
    <rect x="104" y="3" width="16" height="7" rx="1" class="s-to"/>
  </svg>`;
}
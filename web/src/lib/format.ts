import { getLang } from "./i18n";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

/** Clip prose to n words with a clean ellipsis. */
export function clip(t: string | null | undefined, n: number): string {
  const s = String(t ?? "").trim();
  if (!s) return "";
  const w = s.split(/\s+/);
  return w.length > n ? w.slice(0, n).join(" ").replace(/[,;:!?—–]+$/, "") + "…" : s;
}

/** Hard cut to n characters with an ellipsis. */
export function ellipsis(s: string | null | undefined, n: number): string {
  const t = String(s ?? "").trim();
  if (!t) return "";
  if (t.length <= n) return t;
  return t.slice(0, n).replace(/[,;:!?—–]+$/, "").trim() + "…";
}

export const pad2 = (n: number): string => String(n).padStart(2, "0");

/** Edition id `YYYY-MM-DD_to_YYYY-MM-DD` -> `MM-DD`. */
export function shortDate(ed?: string | null): string {
  return ((ed || "").split("_to_")[0] ?? "").slice(5);
}

export function rangeLabel(start?: string | null, end?: string | null): string {
  const parse = (s: string): Date | null => {
    const [y, m, d] = s.split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  };
  const a = start ? parse(start) : null;
  const b = end ? parse(end) : null;
  if (!a || !b) return `${start} → ${end}`;
  const zh = getLang() === "zh";
  if (zh) {
    const wd = ["日", "一", "二", "三", "四", "五", "六"];
    return `${wd[a.getDay()]} ${a.getMonth() + 1}/${a.getDate()} – ${wd[b.getDay()]} ${b.getMonth() + 1}/${b.getDate()}`;
  }
  const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return `${wd[a.getDay()]} ${a.getDate()} ${MON[a.getMonth()] ?? ""} – ${wd[b.getDay()]} ${b.getDate()} ${MON[b.getMonth()] ?? ""} ${b.getFullYear()}`;
}

/** Compressed masthead dateline: `MON 10 AUG – FRI 14 AUG 2026`. */
export function dateline(start?: string | null, end?: string | null): string {
  const parse = (s: string): Date | null => {
    const [y, m, d] = s.split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  };
  const a = start ? parse(start) : null;
  const b = end ? parse(end) : null;
  if (!a || !b) return "WEEKLY BRIEF";
  const wd = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  return `${wd[a.getDay()]} ${a.getDate()} ${(MON[a.getMonth()] ?? "").toUpperCase()} – ${wd[b.getDay()]} ${b.getDate()} ${(MON[b.getMonth()] ?? "").toUpperCase()} ${b.getFullYear()}`;
}
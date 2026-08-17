export type Lang = "en" | "zh";

let lang: Lang = new URLSearchParams(location.search).get("lang") === "zh" ? "zh" : "en";

export function getLang(): Lang {
  return lang;
}

export function setLang(l: Lang): void {
  lang = l;
  document.documentElement.lang = l;
}

/** Pick the zh variant when the UI is in zh and one exists, else the en variant. */
export const pick = (en?: string | null, zh?: string | null): string =>
  lang === "zh" && zh ? zh : en ?? "";

/** Choose a UI string: zh when in zh mode and supplied, else en, else "". */
export const L = (en: string, zh?: string): string => (lang === "zh" && zh ? zh : en);

export const DIR_ZH: Record<string, string> = {
  rising: "升温", accelerating: "加速", hot: "高热度", fading: "消退",
  shifting: "转向", emerging: "新兴", escalating: "升级", new: "新增",
  stable: "持平", high: "高", medium: "中", critical: "关键", low: "低",
} as const;

export const EVID_ZH: Record<string, string> = {
  strong: "证据充分", moderate: "证据中等", emerging: "证据初现",
} as const;

export const dirLabel = (d?: string): string =>
  L((d || "flat").toUpperCase(), DIR_ZH[d || "flat"] || "—");

export const QCAT: Record<string, { en: string; zh: string }> = {
  policy_credibility: { en: "Policy credibility", zh: "政策公信力" },
  market_consequences: { en: "Market consequences", zh: "市场影响" },
  corporate_exposure: { en: "Corporate exposure", zh: "企业敞口" },
  narrative_durability: { en: "Narrative durability", zh: "叙事可持续性" },
};
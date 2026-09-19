import { qs } from "../lib/dom";
import { shortDate } from "../lib/format";
import { L, setLang, getLang, type Lang } from "../lib/i18n";
import type { EditionMeta } from "../lib/api";

export interface EditionSwitcherCallbacks {
  onEdition: (id: string) => void;
  onLang: (lang: Lang) => void;
}

/** Edition <select> + EN/中文 segmented toggle. */
export class EditionSwitcher {
  private sel: HTMLSelectElement;
  private enBtn: HTMLButtonElement;
  private zhBtn: HTMLButtonElement;

  constructor(
    private root: HTMLElement,
    private cb: EditionSwitcherCallbacks,
  ) {
    root.innerHTML = `
      <select class="ctl" id="edition-select" title="edition" aria-label="edition"></select>
      <div class="seg" role="group" aria-label="language">
        <button type="button" id="lang-en" class="active" aria-pressed="true">EN</button>
        <button type="button" id="lang-zh" aria-pressed="false">中文</button>
      </div>`;
    this.sel = qs<HTMLSelectElement>("#edition-select", root)!;
    this.enBtn = qs<HTMLButtonElement>("#lang-en", root)!;
    this.zhBtn = qs<HTMLButtonElement>("#lang-zh", root)!;

    this.sel.addEventListener("change", () => {
      if (this.sel.value) this.cb.onEdition(this.sel.value);
    });
    this.enBtn.addEventListener("click", () => this.applyLang("en"));
    this.zhBtn.addEventListener("click", () => this.applyLang("zh"));
  }

  /** Populate edition options without touching relative layout (fixed width reserved). */
  populate(editions: EditionMeta[], latest: string | null): void {
    this.sel.innerHTML = "";
    for (const e of editions) {
      const o = document.createElement("option");
      o.value = e.id;
      const withheld = e.status === "blocked_no_evidence" || e.status === "synth_failed";
      o.textContent = `${shortDate(e.start_date)} → ${shortDate(e.end_date)}`
        + (withheld ? ` · ${L("data gap", "数据缺口")}` : "");
      this.sel.appendChild(o);
    }
    if (latest) this.sel.value = latest;
  }

  private applyLang(l: Lang): void {
    if (l === getLang()) return;
    setLang(l);
    this.enBtn.classList.toggle("active", l === "en");
    this.zhBtn.classList.toggle("active", l === "zh");
    this.enBtn.setAttribute("aria-pressed", String(l === "en"));
    this.zhBtn.setAttribute("aria-pressed", String(l === "zh"));
    this.cb.onLang(l);
  }
}
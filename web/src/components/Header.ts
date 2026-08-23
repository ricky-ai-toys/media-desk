import { qs } from "../lib/dom";
import { dateline } from "../lib/format";
import { L, type Lang } from "../lib/i18n";
import type { EditionMeta } from "../lib/api";
import { EditionSwitcher } from "./EditionSwitcher";

export interface HeaderCallbacks {
  onEdition: (id: string) => void;
  onLang: (lang: Lang) => void;
  onSearch: (q: string) => void;
  onSearchClear: () => void;
  onExport: () => void;
}

/** Masthead (brand + dateline) and the sticky tools row.
 *  QC state intentionally lives in the footer, not here. */
export class Header {
  private readonly switcher: EditionSwitcher;
  private readonly search: HTMLInputElement;
  private deb: number | undefined;
  private datelineEl: HTMLElement;

  constructor(
    private root: HTMLElement,
    private cb: HeaderCallbacks,
  ) {
    root.innerHTML = `
      <div class="masthead">
        <div class="mast-row">
          <div class="brand">
            <span class="mark" aria-hidden="true">MD</span>
            <div>
              <span class="brand-name">MEDIA<em>DESK</em></span>
              <span class="brand-tag">${L("International Financial Media · Weekly Brief", "国际财经媒体 · 每周简报")}</span>
            </div>
          </div>
          <div class="dateline" id="dateline">—</div>
        </div>
        <div class="tools">
          <div class="tools-in">
            <div id="edition-slot"></div>
            <span class="spacer"></span>
            <button class="btn" id="export-btn">${L("EXPORT", "导出")}</button>
            <input id="search" type="search" placeholder="${L("Search transcripts + wire…", "检索文本与快讯…")}"
              aria-label="${L("Search transcripts and wire", "检索文本与快讯")}">
          </div>
        </div>
      </div>`;

    this.search = qs<HTMLInputElement>("#search", root)!;
    this.datelineEl = qs<HTMLElement>("#dateline", root)!;

    this.switcher = new EditionSwitcher(qs<HTMLElement>("#edition-slot", root)!, {
      onEdition: cb.onEdition,
      onLang: cb.onLang,
    });

    this.search.addEventListener("input", () => this.debouncedSearch());
    this.search.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.search.value) {
        this.search.value = "";
        cb.onSearchClear();
      }
    });
    qs<HTMLButtonElement>("#export-btn", root)!.addEventListener("click", () => cb.onExport());
  }

  populateEditions(editions: EditionMeta[], latest: string | null): void {
    this.switcher.populate(editions, latest);
    const cur = editions.find((e) => e.id === latest);
    if (cur) this.setDateline(cur.start_date, cur.end_date);
  }

  setDateline(start?: string | null, end?: string | null): void {
    this.datelineEl.innerHTML = dateline(start, end);
  }

  private debouncedSearch(): void {
    window.clearTimeout(this.deb);
    const q = this.search!.value.trim();
    if (!q) {
      this.cb.onSearchClear();
      return;
    }
    if (q.length < 2) return;
    this.deb = window.setTimeout(() => this.cb.onSearch(q), 380);
  }
}
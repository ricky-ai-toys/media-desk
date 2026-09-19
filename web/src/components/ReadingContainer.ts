import { qs } from "../lib/dom";
import type { Desk, EditionMeta, LifecycleTrack, SourceHealth } from "../lib/api";
import { renderBrief } from "../views/BriefView";
import { renderSearch } from "../views/SearchView";

/** Owns #view: render states, SSE-driven reloads, and the edition-swap transition. */
export class ReadingContainer {
  private readonly root: HTMLElement;
  private swapTimer: number | undefined;
  private gapWeeks: EditionMeta[] = [];
  private current: {
    kind: "brief" | "search" | "error";
    desk?: Desk;
    sources?: SourceHealth[];
    lifecycle?: LifecycleTrack[];
    prevEdition?: string | null;
  } = { kind: "error" };

  constructor(root: HTMLElement) {
    this.root = root;
  }

  /** Weeks withheld for lack of episode evidence — surfaced as a banner on the brief. */
  setGapWeeks(weeks: EditionMeta[]): void {
    this.gapWeeks = weeks;
  }

  showSkeleton(): void {
    this.abortSwap();
    this.root.className = "reading";
    this.root.innerHTML = `
      <div class="skeleton" aria-hidden="true">
        <div class="sk lead-1"></div>
        <div class="sk lead-2"></div>
        <div class="sk w80"></div>
        <div class="sk w60"></div>
        <div class="sk w80"></div>
        <div class="sk w60"></div>
        <div class="sk w40"></div>
      </div>`;
  }

  showBrief(desk: Desk, sources: SourceHealth[] = [], lifecycle: LifecycleTrack[] = [], prevEdition: string | null = null): void {
    this.current = { kind: "brief", desk, sources, lifecycle, prevEdition };
    this.swap(() => renderBrief(desk, sources, lifecycle, prevEdition, this.gapWeeks));
  }

  showSearch(query: string, results: { title?: string; source_name?: string | null; kind?: string; pub_date?: string | null; snip?: string | null }[]): void {
    this.current = { kind: "search" };
    this.swap(() => renderSearch(query, results));
  }

  showError(msg: string): void {
    this.current = { kind: "error" };
    this.abortSwap();
    this.root.className = "reading";
    this.root.innerHTML = `<div class="sec"><div class="empty">${msg}</div></div>`;
  }

  refresh(): void {
    if (this.current.kind === "brief" && this.current.desk) {
      this.showBrief(this.current.desk, this.current.sources ?? [], this.current.lifecycle ?? [], this.current.prevEdition ?? null);
    }
  }

  /** Fade out, rebuild, fade the rows back in like a tape refresh. */
  private swap(build: () => string): void {
    this.abortSwap();
    this.root.classList.add("sub");
    this.root.classList.add("swap");
    this.swapTimer = window.setTimeout(() => {
      this.root.innerHTML = build();
      this.root.classList.remove("swap");
    }, 160);
  }

  private abortSwap(): void {
    if (this.swapTimer !== undefined) window.clearTimeout(this.swapTimer);
    this.swapTimer = undefined;
  }
}
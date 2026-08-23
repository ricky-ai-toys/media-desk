import { qs } from "../lib/dom";
import { getLang, L } from "../lib/i18n";

const STAGE_ZH: Record<string, string> = {
  bootstrap: "初始化", ingest: "采集", analyze: "分析", synth: "合成", qc: "质检",
};

const STATUS_ZH: Record<string, string> = {
  idle: "空闲", queued: "排队中", running: "进行中", done: "完成", failed: "失败",
};

/** Colophon: pipeline state + QC verdict (left) and a tabular clock (right). */
export class Footer {
  private readonly pipe: HTMLElement;
  private readonly clock: HTMLElement;
  private readonly qcEl: HTMLElement;
  private lastQc: { status: string; blocks?: string[] } | null = null;

  constructor(
    private root: HTMLElement,
    initialPipe: string,
  ) {
    const zh = getLang() === "zh";
    root.innerHTML = `
      <footer class="colophon">
        <span><b>MEDIA DESK</b> · <span id="pipe-state">${initialPipe}</span> <span class="qc" id="foot-qc" hidden></span></span>
        <span class="clock" id="clock" aria-live="off">—</span>
      </footer>`;
    this.pipe = qs<HTMLElement>("#pipe-state", root)!;
    this.clock = qs<HTMLElement>("#clock", root)!;
    this.qcEl = qs<HTMLElement>("#foot-qc", root)!;
    window.setInterval(() => {
      this.clock.textContent = new Date().toLocaleTimeString("en-GB");
    }, 1000);
    this.clock.textContent = new Date().toLocaleTimeString("en-GB");
  }

  setPipe(p: { stage?: string; status?: string }): void {
    const zh = getLang() === "zh";
    const stage = p.stage ?? "?";
    const status = p.status ?? "?";
    this.pipe.textContent = zh
      ? `管线: ${STAGE_ZH[stage] ?? stage} | ${STATUS_ZH[status] ?? status}`
      : `pipeline: ${stage} | ${status}`;
  }

  /** QC verdict lives at the very end of the page, per editorial preference. */
  setQc(qc: { status: string; blocks?: string[] } | null): void {
    this.lastQc = qc;
    if (!qc) {
      this.qcEl.hidden = true;
      return;
    }
    const ok = qc.status === "PASS";
    const n = (qc.blocks ?? []).length;
    this.qcEl.textContent = ok
      ? L("QC PASS", "质检通过")
      : L(`QC FAIL${n ? ` · ${n}` : ""}`, `质检未通过${n ? ` · ${n}` : ""}`);
    this.qcEl.className = `qc ${ok ? "pass" : "fail"}`;
    this.qcEl.title = ok
      ? L("Editorial quality checks passed", "编辑质检全部通过")
      : L("Details at the end of the page", "详情见页面末尾");
  }

  /** Re-render stored state after a language switch. */
  refresh(): void {
    this.setQc(this.lastQc);
  }
}
import { qs } from "../lib/dom";
import { getLang } from "../lib/i18n";

const STAGE_ZH: Record<string, string> = {
  bootstrap: "初始化", ingest: "采集", analyze: "分析", synth: "合成", qc: "质检",
};

const STATUS_ZH: Record<string, string> = {
  idle: "空闲", queued: "排队中", running: "进行中", done: "完成", failed: "失败",
};

/** Colophon: pipeline state (left) and a tabular clock (right, zero width drift). */
export class Footer {
  private readonly pipe: HTMLElement;
  private readonly clock: HTMLElement;

  constructor(
    private root: HTMLElement,
    initialPipe: string,
  ) {
    const zh = getLang() === "zh";
    root.innerHTML = `
      <footer class="colophon">
        <span><b>MEDIA DESK</b> · <span id="pipe-state">${initialPipe}</span></span>
        <span class="clock" id="clock" aria-live="off">—</span>
      </footer>`;
    this.pipe = qs<HTMLElement>("#pipe-state", root)!;
    this.clock = qs<HTMLElement>("#clock", root)!;
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
}
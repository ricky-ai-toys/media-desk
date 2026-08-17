import { esc } from "../lib/dom";
import { clip } from "../lib/format";
import { L } from "../lib/i18n";
import type { SearchHit } from "../lib/api";

const mark = (s: string, q: string): string => {
  if (!q) return esc(s);
  const qq = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`(${qq})`, "ig");
  return esc(s).replace(re, "<mark>$1</mark>");
};

export function renderSearch(query: string, results: SearchHit[]): string {
  const hits = results.slice(0, 40);
  const q = query.trim();
  const body = hits.length
    ? `<div class="hits">${hits
        .map(
          (x) => `
        <div class="hit">
          <b class="hit-title">${mark(x.title || x.source_name || "—", q)}</b>
          <span class="s"> [${esc(x.kind || "")}] ${mark(x.source_name ?? "", q)} ${esc(x.pub_date ?? "")}</span>
          ${x.snip ? `<div class="hit-snip">${mark(clip(x.snip, 24), q)}</div>` : ""}
        </div>`,
        )
        .join("")}</div>`
    : `<div class="empty">${L("No results", "无结果")}</div>`;
  return `
    <section class="sec">
      <header class="sec-head">
        <h2 class="sec-lab">${esc(L("Search", "检索"))}: ${esc(query)}</h2>
        <span class="sec-hint">${hits.length} ${L("hits · Esc to close", "条结果 · 按 Esc 关闭")}</span>
      </header>
      <div class="sec-body">${body}</div>
    </section>`;
}

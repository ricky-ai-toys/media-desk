import "./styles.css";
import { qs } from "./lib/dom";
import { api, type Desk, type LifecycleTrack, type Meta } from "./lib/api";
import { getLang } from "./lib/i18n";
import { Header } from "./components/Header";
import { ReadingContainer } from "./components/ReadingContainer";
import { Footer } from "./components/Footer";

const state: { edition: string | null; desk: Desk | null; meta: Meta | null; lifecycle: LifecycleTrack[] } = {
  edition: null,
  desk: null,
  meta: null,
  lifecycle: [],
};

function prevEditionOf(meta: Meta, edition: string): string | null {
  const eds = (meta.editions || []).filter((e) => (e.id ?? "") < edition);
  return eds.length ? (eds[eds.length - 1]?.id ?? null) : null;
}

function setTitle(edition: string, lang: "en" | "zh"): void {
  const range = edition.replace(/_to_/, " → ");
  document.title = lang === "zh"
    ? `国际财经媒体周报 · ${range}`
    : `International Financial Media Weekly · ${range}`;
}

const headerRoot = qs<HTMLElement>("#app-header")!;
const viewRoot = qs<HTMLElement>("#view")!;
const footerRoot = qs<HTMLElement>("#app-footer")!;

const reading = new ReadingContainer(viewRoot);
reading.showSkeleton();

const footer = new Footer(footerRoot, getLang() === "zh" ? "管线: —" : "pipeline: —");

const header = new Header(headerRoot, {
  onEdition: (id) => loadDesk(id),
  onLang: () => {
    footer.setPipe(state.meta?.pipeline ?? {});
    if (state.edition) {
      setTitle(state.edition, getLang());
      loadDesk(state.edition);
    }
  },
  onSearch: (q) => {
    api<{ results: NonNullable<unknown>[] }>("/api/search?q=" + encodeURIComponent(q))
      .then((r) => {
        const results = (r.results || []) as unknown as {
          title?: string;
          source_name?: string | null;
          kind?: string;
          pub_date?: string | null;
          snip?: string | null;
        }[];
        reading.showSearch(q, results);
      })
      .catch((e) => reading.showError(String(e.message ?? e)));
  },
  onSearchClear: () => {
    if (state.desk) reading.showBrief(state.desk);
  },
  onExport: () => {
    if (state.edition) window.open(`/export/${encodeURIComponent(state.edition)}/email`, "_blank");
  },
});

async function loadDesk(edition: string): Promise<void> {
  state.edition = edition;
  try {
    const desk = await api<Desk>("/api/desk?edition=" + encodeURIComponent(edition));
    state.desk = desk;
    setTitle(edition, getLang());
    header.setQc(desk.qc);
    header.setDateline(desk.start, desk.end);
    const prev = state.meta ? prevEditionOf(state.meta, edition) : null;
    reading.showBrief(desk, state.meta?.sources ?? [], state.lifecycle, prev);
  } catch (e) {
    reading.showError(String(e instanceof Error ? e.message : e));
  }
}

async function boot(): Promise<void> {
  try {
    const [meta, lifecycle] = await Promise.all([
      api<Meta>("/api/meta"),
      api<{ tracks?: LifecycleTrack[] }>("/api/lifecycle").catch(() => ({ tracks: [] })),
    ]);
    state.meta = meta;
    state.lifecycle = lifecycle.tracks || [];
    header.populateEditions(meta.editions, meta.latest);
    footer.setPipe(meta.pipeline ?? {});
    if (meta.latest && !state.edition) {
      state.edition = meta.latest;
      await loadDesk(meta.latest);
    } else if (state.edition) {
      await loadDesk(state.edition);
    } else {
      reading.showError("no edition found");
    }
  } catch (e) {
    reading.showError(String(e instanceof Error ? e.message : e));
  }
}

/* ---------- SSE pipeline events ---------- */
function wireSse(): void {
  const es = new EventSource("/api/stream");
  es.addEventListener("pipeline", (ev) => {
    try {
      const p = JSON.parse(ev.data) as { stage?: string; status?: string };
      footer.setPipe(p);
      if (p.status === "done") void boot();
    } catch {
      /* ignore malformed frames */
    }
  });
}

void boot();
wireSse();
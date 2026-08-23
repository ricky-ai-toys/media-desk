/* Data contracts mirroring the v5/schema-v2 payloads served by /api/desk. */

export interface EditionMeta {
  id: string;
  start_date: string;
  end_date: string;
  status: string;
}

export interface SourceHealth {
  id: string;
  name: string;
  outlet: string;
  kind: string;
  episodes: number;
  articles: number;
  last_run: string | null;
  last_ok: number;
}

export interface Meta {
  latest: string | null;
  editions: EditionMeta[];
  sources: SourceHealth[];
  pipeline?: { stage?: string; status?: string };
}

export interface AgendaItem {
  rank?: number;
  title_en?: string;
  title_zh?: string;
  summary_en?: string;
  summary_zh?: string;
  priority?: string;
  momentum?: string;
  evidence?: string;
  direction?: string;
  coverage?: number;
  score?: number;
  driver_en?: string;
  driver_zh?: string;
  next_test_en?: string;
  next_test_zh?: string;
  stakes_en?: string;
  stakes_zh?: string;
}

export interface Narrative {
  title_en?: string;
  title_zh?: string;
  from_en?: string;
  from_zh?: string;
  to_en?: string;
  to_zh?: string;
  driver_en?: string;
  driver_zh?: string;
  why_en?: string;
  why_zh?: string;
  next_test_en?: string;
  next_test_zh?: string;
}

export interface CommsBox {
  title_en?: string;
  title_zh?: string;
  implication_en?: string;
  implication_zh?: string;
  risky_en?: string;
  risky_zh?: string;
  questions_likely_en?: string[];
  questions_likely_zh?: string[];
  evidence_to_prepare_en?: string[];
  evidence_to_prepare_zh?: string[];
}

export interface PrCounsel {
  risk_en?: string;
  risk_zh?: string;
  avoid_en?: string;
  avoid_zh?: string;
  opportunity_en?: string;
  opportunity_zh?: string;
  prepare_en?: string;
  prepare_zh?: string;
}

export interface QuestionGroup {
  category?: string;
  questions_en?: string[];
  questions_zh?: string[];
}

export interface MediaExchange {
  premise_en?: string;
  premise_zh?: string;
  response_en?: string;
  response_zh?: string;
  lesson_en?: string;
  lesson_zh?: string;
  likely_to_recur?: boolean;
}

export interface InterviewGroup {
  title_en?: string;
  title_zh?: string;
  role_en?: string;
  role_zh?: string;
  questions_en?: string[];
  questions_zh?: string[];
}

export interface Watchpoint {
  trigger_en?: string;
  trigger_zh?: string;
  shift_en?: string;
  shift_zh?: string;
  affected_en?: string;
  affected_zh?: string;
  priority_raises_en?: string;
  priority_raises_zh?: string;
}

export interface EvidenceStatus {
  section?: string;
  status?: string;
  note?: string;
}

export interface PrCounsel {
  risk_en?: string;
  risk_zh?: string;
  avoid_en?: string;
  avoid_zh?: string;
  opportunity_en?: string;
  opportunity_zh?: string;
}

export interface DeskData {
  report_title?: string;
  thesis_en?: string;
  thesis_zh?: string;
  week_summary_en?: string;
  week_summary_zh?: string;
  monitored_outlets?: string[];
  source_file_count?: number;
  episode_count?: number;
  comms_boxes?: CommsBox[];
  question_groups?: QuestionGroup[];
  top_questions_next_week_en?: string[];
  top_questions_next_week_zh?: string[];
  media_exchanges?: MediaExchange[];
  watchpoints?: Watchpoint[];
  evidence_statuses?: EvidenceStatus[];
  pr_counsel?: PrCounsel;
  watchlist_en?: string[];
  watchlist_zh?: string[];
  warnings?: string[];
  recurring_questions_en?: Array<string | { text?: string; q?: string }>;
  recurring_questions_zh?: string[];
  week_ahead_events?: { date?: string; event_en?: string; event_zh?: string; why_en?: string; why_zh?: string }[];
}

export interface LifecycleTrack {
  label?: string;
  title_zh?: string;
  first_seen?: string;
  last_seen?: string;
  phase?: string;
  rank_delta?: number;
}

export interface TickerItem {
  date?: string;
  show?: string;
  /** Who the exchange was with — highlighted instead of the show name. */
  guest?: string | null;
  org?: string | null;
  tone?: string;
  question?: string;
  /** false when the wording was not found verbatim in the transcript */
  verified?: boolean;
}

export interface PressureItem {
  date?: string;
  show?: string;
  pressure?: number;
  challenges?: number;
  softballs?: number;
  evasions?: number;
  sampled?: number;
}

export interface LeadLag {
  topic?: string;
  tv_first?: string | null;
  wire_first?: string | null;
  wire_lead_days?: number | null;
  tv_count?: number;
  wire_count?: number;
}

export interface Desk {
  edition: string;
  start: string;
  end: string;
  status: string;
  qc: QcState | null;
  data: DeskData;
  agenda: AgendaItem[];
  narratives: Narrative[];
  interview_groups?: InterviewGroup[];
  ticker?: TickerItem[];
  pressure?: PressureItem[];
  framing?: { collisions?: unknown[]; lead_lag?: LeadLag[] };
}

export interface QcCheck {
  check?: string;
  pass?: boolean;
  detail?: string;
  blockable?: boolean;
}

export interface QcState {
  status: string;
  blocked?: boolean;
  blocks?: string[];
  checks?: QcCheck[];
}

export interface SearchHit {
  title?: string;
  source_name?: string | null;
  kind?: string;
  pub_date?: string | null;
  snip?: string | null;
}

export interface SearchResults {
  query: string;
  results: SearchHit[];
}

export async function api<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}
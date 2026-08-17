/** HTML-escape untrusted text. */
export const esc = (s: string | null | undefined): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);

/** Normalize a payload field to a list. */
export const asList = <T>(v: T | T[] | null | undefined): T[] =>
  Array.isArray(v) ? v : v ? [v] : [];

export const qs = <T extends HTMLElement>(sel: string, root: ParentNode = document): T | null =>
  root.querySelector<T>(sel);

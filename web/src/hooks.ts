import { useEffect, useState } from "react";

export function useData<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    fn().then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

export type Page = "today" | "patterns" | "nudges";
const PAGES: Page[] = ["today", "patterns", "nudges"];

// the page lives in the URL hash (#patterns), so reloading keeps you where you were
export function usePage(): [Page, (p: Page) => void] {
  const read = () => {
    const h = window.location.hash.slice(1) as Page;
    return PAGES.includes(h) ? h : "today";
  };
  const [page, setPage] = useState<Page>(read);
  useEffect(() => {
    const on = () => setPage(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [page, (p: Page) => (window.location.hash = p)];
}

import { useEffect, useState } from "react";

export type ScreenId = "overview" | "ask" | "sites" | "jobs" | "opportunities" | "proof" | "control" | "whatif" | "clients" | "reports" | "trust";

const SCREEN_IDS: ScreenId[] = ["overview", "ask", "sites", "jobs", "opportunities", "control", "whatif", "clients", "reports"];
const parts = () => location.hash.slice(2).split("?");

// Hash routing: each screen has its own link and the browser back button works, with no router library.
// A link may carry a query after the screen name (#/ask?from=control); it never changes which screen opens.
export function useRoute(): [ScreenId, (id: ScreenId) => void] {
  const read = () => (parts()[0] || "overview") as ScreenId;
  const [screen, setScreen] = useState<ScreenId>(read);
  useEffect(() => {
    const on = () => setScreen(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [screen, (id) => (location.hash = `/${id}`)];
}

// The screen the analyst was opened from, so it can suggest questions about that screen.
export function askedFrom(): ScreenId | null {
  const from = new URLSearchParams(parts()[1] ?? "").get("from") as ScreenId | null;
  return from && from !== "ask" && SCREEN_IDS.includes(from) ? from : null;
}

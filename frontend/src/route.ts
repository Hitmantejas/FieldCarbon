import { useEffect, useState } from "react";

export type ScreenId = "overview" | "sites" | "jobs" | "opportunities" | "control" | "whatif" | "clients" | "reports";

// Hash routing: each screen has its own link and the browser back button works, with no router library.
export function useRoute(): [ScreenId, (id: ScreenId) => void] {
  const read = () => (location.hash.slice(2) || "overview") as ScreenId;
  const [screen, setScreen] = useState<ScreenId>(read);
  useEffect(() => {
    const on = () => setScreen(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [screen, (id) => (location.hash = `/${id}`)];
}

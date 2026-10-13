import { createContext, useContext, type ReactNode } from "react";
import { useApi, type SourceInfo } from "./api";

const SourcesContext = createContext<Record<string, SourceInfo>>({});

// Figures carry source ids; this resolves them to titles and link status for the working sheet.
export function SourcesProvider({ children }: { children: ReactNode }) {
  const { data } = useApi<SourceInfo[]>("/api/sources");
  const byId = Object.fromEntries((data ?? []).map((s) => [s.source_id, s]));
  return <SourcesContext.Provider value={byId}>{children}</SourcesContext.Provider>;
}

export const useSources = () => useContext(SourcesContext);

const LINK_TEXT: Record<string, string> = {
  verified: "Link checked",
  unverified: "Link not checked yet",
  "missing-link": "No link yet",
};

export function linkText(status: string): string {
  return LINK_TEXT[status] ?? status.replace(/[-_]/g, " ");
}

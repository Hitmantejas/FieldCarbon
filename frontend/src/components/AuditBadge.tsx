import type { Narrative } from "../fleetApi";

// Says in words who wrote the summary: Gemini, with every number checked by code, or the fixed standard wording.
export function AuditBadge({ narrative }: { narrative: Narrative }) {
  const gemini = narrative.narrative_source === "gemini";
  const title = gemini
    ? `Written by Gemini. Code checked all ${narrative.numbers_checked} numbers against the figures below, and that each figure has its label.`
    : "Standard wording filled in by code, not written by AI.";
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span title={title} className={`stamp ${gemini ? "stamp-measured" : "stamp-estimated"}`}>
        {gemini ? "Audited by code" : "Standard wording"}
      </span>
      <span className="text-sm text-ink-soft">{gemini ? `Written by Gemini · ${narrative.numbers_checked} numbers checked by code` : "Not written by AI"}</span>
    </span>
  );
}

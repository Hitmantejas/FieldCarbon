import type { ReactNode } from "react";

// Each kind of section has its own leaf, so a heading is never mistaken for a caption.
const LEAF = {
  solid: "bg-moss",
  mark: "bg-mark ring-2 ring-moss",
  dashed: "border-2 border-moss",
  muted: "border-2 border-ink-soft",
};

interface Props {
  id: string;
  title: string;
  tone: keyof typeof LEAF;
  note?: string;
  aside?: ReactNode;
}

export function SectionHead({ id, title, tone, note, aside }: Props) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <h2 id={id} className={`flex flex-1 flex-wrap items-baseline gap-x-3 gap-y-1 font-display text-[1.75rem] font-semibold leading-tight ${tone === "muted" ? "text-ink-soft" : ""}`}>
        <span aria-hidden="true" className={`inline-block size-3 shrink-0 -translate-y-0.5 rounded-[50%_0] ${LEAF[tone]}`} />
        {title}
        {note && <span className="font-mono text-xs font-normal uppercase tracking-widest text-ink-soft">{note}</span>}
      </h2>
      {aside}
    </div>
  );
}

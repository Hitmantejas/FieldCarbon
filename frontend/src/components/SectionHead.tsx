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
      <h2 id={id} className={`min-w-0 flex-1 basis-64 font-display text-[1.75rem] font-semibold leading-tight ${tone === "muted" ? "text-ink-soft" : ""}`}>
        <span aria-hidden="true" className={`mr-3 inline-block size-3 -translate-y-0.5 rounded-[50%_0] ${LEAF[tone]}`} />
        {title}
        {note && <span className="ml-3 inline-block font-mono text-xs font-normal uppercase tracking-widest text-ink-soft">{note}</span>}
      </h2>
      {aside}
    </div>
  );
}

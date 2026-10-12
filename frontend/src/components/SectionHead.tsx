import type { ReactNode } from "react";

// Each kind of section looks different, so a heading is never mistaken for a caption.
const TONE = {
  solid: "bg-ink text-paper",
  mark: "bg-mark text-on-mark",
  dashed: "border-2 border-dashed border-ink",
  muted: "border-2 border-rule text-ink-soft",
};

interface Props {
  id: string;
  title: string;
  tone: keyof typeof TONE;
  note?: string;
  aside?: ReactNode;
}

export function SectionHead({ id, title, tone, note, aside }: Props) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-3">
      <h2 id={id} className={`flex-1 px-3 py-2 font-display text-2xl font-extrabold uppercase leading-none tracking-wide ${TONE[tone]}`}>
        {title}
        {note && <span className="ml-3 font-mono text-xs font-normal tracking-widest">{note}</span>}
      </h2>
      {aside}
    </div>
  );
}

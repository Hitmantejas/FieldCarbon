import type { Figure } from "../api";
import { Stamp } from "./Stamp";

interface Props {
  title: string;
  shown: string;
  unit: string;
  figure?: Figure; // a plain count has no confidence label
  onOpen?: () => void;
  highlight?: boolean;
}

// One headline figure: opens its working sheet, carries its confidence label as text.
export function Tile({ title, shown, unit, figure, onOpen, highlight }: Props) {
  const body = (
    <>
      <span className={`font-mono text-xs uppercase tracking-widest ${highlight ? "" : "text-ink-soft"}`}>{title}</span>
      <span className="font-display text-5xl font-semibold leading-none">
        {shown}
        <span className="ml-2 font-mono text-sm font-normal">{unit}</span>
      </span>
      {figure ? <Stamp label={figure.label} /> : <span className="h-5" />}
    </>
  );
  const box = `flex min-h-32 flex-col justify-between gap-3 rounded-3xl p-5 text-left ${highlight ? "bg-mark text-on-mark [&_.stamp]:border-on-mark [&_.stamp:not(.stamp-measured)]:text-on-mark [&_.stamp-measured]:bg-on-mark [&_.stamp-measured]:text-mark" : "bg-tint"}`;
  if (!figure || !onOpen) return <div className={box}>{body}</div>;
  return (
    <button
      onClick={onOpen}
      aria-label={`${title}: ${shown} ${unit}, ${figure.label}. Show how it was worked out.`}
      className={`${box} transition-colors ${highlight ? "" : "hover:bg-mark/40"}`}
    >
      {body}
    </button>
  );
}

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

// One headline figure: opens its working sheet, carries its confidence stamp as text.
export function Tile({ title, shown, unit, figure, onOpen, highlight }: Props) {
  const body = (
    <>
      <span className="font-mono text-xs uppercase tracking-widest">{title}</span>
      <span className="font-display text-5xl font-extrabold leading-none">
        {shown}
        <span className="ml-2 font-mono text-sm font-normal">{unit}</span>
      </span>
      {figure ? <Stamp label={figure.label} /> : <span className="h-5" />}
    </>
  );
  const box = `flex min-h-32 flex-col justify-between gap-3 border-r-2 border-dashed border-ink p-4 text-left last:border-r-0 ${highlight ? "bg-mark text-on-mark [&_.stamp]:border-on-mark" : ""}`;
  if (!figure || !onOpen) return <div className={box}>{body}</div>;
  return (
    <button
      onClick={onOpen}
      aria-label={`${title}: ${shown} ${unit}, ${figure.label}. Show how it was worked out.`}
      className={`${box} transition-colors hover:bg-ink/10`}
    >
      {body}
    </button>
  );
}

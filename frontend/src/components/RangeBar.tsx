interface Props {
  low: number;
  high: number;
  max: number;
  description: string;
}

// Bracketed bar: the filled span runs from the low to the high figure on a 0..max track.
export function RangeBar({ low, high, max, description }: Props) {
  return (
    <div role="img" aria-label={description} className="relative h-5 border-b-2 border-ink-soft">
      <div
        className="span-in absolute inset-y-0 border-x-2 border-ink bg-mark"
        style={{ left: `${(low / max) * 100}%`, width: `${((high - low) / max) * 100}%` }}
      />
    </div>
  );
}

// Plain share of a whole, for "how much of the fuel".
export function ShareBar({ pct, description }: { pct: number; description: string }) {
  return (
    <div role="img" aria-label={description} className="h-3 border-2 border-ink">
      <div className="span-in h-full bg-ink" style={{ width: `${pct}%` }} />
    </div>
  );
}

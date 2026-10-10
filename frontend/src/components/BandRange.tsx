interface Props {
  yours: number;
  low: number;
  high: number;
  description: string;
}

// The typical range is a bracket on a 0..max track; the farm's own figure is a heavy tick.
export function BandRange({ yours, low, high, description }: Props) {
  const max = Math.max(yours, high) * 1.12;
  const at = (v: number) => `${(v / max) * 100}%`;
  return (
    <div role="img" aria-label={description} className="relative mt-5 h-5 border-b-2 border-ink-soft">
      <div
        className="span-in absolute inset-y-0 border-x-2 border-ink bg-ink/15"
        style={{ left: at(low), width: `${((high - low) / max) * 100}%` }}
      />
      <div className="span-in absolute -top-3 bottom-0 w-1.5 -translate-x-1/2 bg-ink" style={{ left: at(yours) }} />
    </div>
  );
}

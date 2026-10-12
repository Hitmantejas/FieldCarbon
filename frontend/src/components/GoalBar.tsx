interface Props {
  low: number;
  high: number;
  target: number;
  max: number;
  description: string;
  goalLabel?: string;
}

const pct = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

// The yellow bar is what the idea could cut. The dashed line is the farmer's goal and slides when it changes.
export function GoalBar({ low, high, target, max, description, goalLabel }: Props) {
  const at = (v: number) => `${(v / max) * 100}%`;
  return (
    <div role="img" aria-label={description} className="mt-8">
      <div className="relative h-6 border-b-2 border-ink-soft">
        {low === high ? (
          <div className="span-in absolute -top-1 bottom-0 w-1.5 -translate-x-1/2 bg-ink" style={{ left: at(low) }} />
        ) : (
          <div
            className="span-in absolute inset-y-0 border-x-2 border-ink bg-mark"
            style={{ left: at(low), width: `${((high - low) / max) * 100}%` }}
          />
        )}
        <div
          aria-hidden="true"
          className="absolute -top-2 bottom-0 transition-[left] duration-500 ease-out motion-reduce:transition-none"
          style={{ left: at(target) }}
        >
          <span className="absolute -top-5 left-0 -translate-x-1/2 whitespace-nowrap bg-ink px-1 font-mono text-[0.65rem] uppercase tracking-widest text-paper">
            {goalLabel ?? `Goal ${pct(target)}%`}
          </span>
          <span className="block h-full border-l-4 border-dashed border-ink" />
        </div>
      </div>
      <div className="mt-1 flex justify-between font-mono text-[0.7rem] text-ink-soft" aria-hidden="true">
        <span>0%</span>
        <span>{Math.round(max)}%</span>
      </div>
    </div>
  );
}

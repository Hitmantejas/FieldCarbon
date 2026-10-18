interface Props {
  low: number;
  high: number;
  max: number;
  description: string;
}

// Range capsule: the filled span runs from the low to the high figure on a 0..max track.
export function RangeBar({ low, high, max, description }: Props) {
  return (
    <div role="img" aria-label={description} className="relative h-5 rounded-full bg-tint">
      <div
        className="span-in absolute inset-y-0 rounded-full border-2 border-moss bg-mark"
        style={{ left: `${(low / max) * 100}%`, width: `max(${((high - low) / max) * 100}%, 6px)` }}
      />
    </div>
  );
}

import type { Figure } from "./api";
import { gbpFull, litres, tonnes } from "./format";

// A figure is either one value or a low-high range; both read as a range.
const bounds = (f: Figure | null): [number, number] | null => {
  const lo = f?.low ?? f?.value, hi = f?.high ?? f?.value;
  return lo == null || hi == null ? null : [lo, hi];
};

// A saving range in words. A negative litres figure means the idea burns more fuel (HVO), so we say that.
export function litresText(f: Figure | null): string {
  const b = bounds(f);
  if (!b) return "not worked out";
  const [lo, hi] = b;
  if (hi < 0) return `${litres(-hi)}${lo === hi ? "" : ` to ${litres(-lo)}`} more litres`;
  return lo === hi ? `${litres(lo)} litres` : `${litres(lo)} to ${litres(hi)} litres`;
}
// Money: a negative figure is a cost, so we say "more" rather than show a minus sign.
export const absRange = (f: Figure, fmt: (n: number) => string) => {
  const [lo, hi] = bounds(f) ?? [0, 0];
  const [a, b] = [Math.abs(lo), Math.abs(hi)].sort((x, y) => x - y);
  return a === b ? fmt(a) : `${fmt(a)} to ${fmt(b)}`;
};
export const co2Text = (f: Figure | null) => {
  const b = bounds(f);
  return b ? (b[0] === b[1] ? tonnes(b[0]) : `${tonnes(b[0])} to ${tonnes(b[1])}`) + " CO2e" : "not worked out";
};
export const moneyText = (f: Figure | null) => {
  const bd = bounds(f);
  if (!bd) return "not worked out";
  const [a, b] = bd;
  const word = (n: number) => (n < 0 ? `-${gbpFull(-n)}` : gbpFull(n));
  return a === b ? word(a) : `${word(a)} to ${word(b)}`;
};

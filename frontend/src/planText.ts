import type { Figure, Intervention } from "./api";
import { gbpFull, pctText } from "./format";

// What the cost helpers need from an idea: both the Plan and the Report pass these.
type CostItem = Pick<Intervention, "figures" | "cost_kind">;

export const span = (f: Figure, fmt: (n: number) => string) =>
  f.low === f.high ? fmt(f.low!) : `${fmt(f.low!)} to ${fmt(f.high!)}`;

export const tonnesSpan = (f: Figure) => {
  const t = (kg: number) => (kg / 1000).toFixed(1);
  return f.low === f.high ? t(f.low!) : `${t(f.low!)} to ${t(f.high!)}`;
};

export const sizeText = (low: number, high: number) =>
  low === high ? `about ${pctText(low)}%` : `${pctText(low)}% to ${pctText(high)}%`;

export function yearsText(low: number, high: number): string {
  const one = (n: number) => (n < 1 ? "under a year" : `${Math.round(n)} ${Math.round(n) === 1 ? "year" : "years"}`);
  if (high < 1) return "under a year";
  if (low >= 1 && Math.round(low) === Math.round(high)) return one(low);
  return low < 1 ? `under a year to ${one(high)}` : `${Math.round(low)} to ${one(high)}`;
}

export const perUnit = (f: Figure) => f.unit.replace(/^GBP /, "").replace(", retrofit", "");

// Working the land and sowing: the cost falls when the figures are negative.
export function landCost(low: number, high: number): { sentence: string; short: string } {
  const noEquipment = "It does not count the cost of any new equipment, such as a drill: we have no price for that.";
  if (high <= 0) {
    const amount = `${high === 0 ? `up to ${gbpFull(-low)}` : `${gbpFull(-high)} to ${gbpFull(-low)}`} a year`;
    return {
      sentence: `Could cut the cost of working the land and sowing by ${amount}. This includes the fuel you save. ${noEquipment}`,
      short: `Cuts yearly costs by ${amount}`,
    };
  }
  const amount = `${gbpFull(Math.max(low, 0))} to ${gbpFull(high)} a year`;
  return { sentence: `Could raise the cost of working the land and sowing by ${amount}. ${noEquipment}`, short: `Raises yearly costs by ${amount}` };
}

// The short figure shown at the top of the cost sheet.
export function costShort(item: CostItem): string {
  const f = item.figures;
  if (item.cost_kind === "capex_one_off") return `${span(f.cost!, gbpFull)} ${perUnit(f.cost!)}`;
  const run = f.running_cost_change_gbp!;
  if (item.cost_kind === "operating_cost_per_area_change") return landCost(run.low!, run.high!).short;
  return `${gbpFull(run.low!)} to ${gbpFull(run.high!)} more a year`;
}

export function costLine(item: CostItem): string {
  const f = item.figures;
  if (!f.cost) return "We do not have a price for this yet.";
  if (item.cost_kind === "capex_one_off") {
    const buy = `Costs about ${span(f.cost, gbpFull)} ${perUnit(f.cost)}.`;
    if (!f.payback_years) return buy;
    const time = yearsText(f.payback_years.low!, f.payback_years.high!);
    return time === "under a year"
      ? `${buy} It would pay for itself in under a year.`
      : `${buy} It would take about ${time} of fuel savings to pay for itself.`;
  }
  const run = f.running_cost_change_gbp!;
  if (item.cost_kind === "operating_cost_per_area_change") return landCost(run.low!, run.high!).sentence;
  return `Would cost you about ${gbpFull(run.low!)} to ${gbpFull(run.high!)} more a year. We only have a rough price for HVO: ask a fuel supplier for a quote.`;
}

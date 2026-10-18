const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

export const pctText = (n: number) => (n >= 10 ? n.toFixed(0) : n.toFixed(1));
export const litres = (n: number) => whole.format(n);
export const tonnes = (kg: number) => `${(kg / 1000).toFixed(1)} t`;
export const gbp = (n: number) => (n >= 1000 ? `£${(n / 1000).toFixed(1)}k` : `£${whole.format(n)}`);
export const gbpFull = (n: number) => `£${whole.format(n)}`;

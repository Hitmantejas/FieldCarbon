import type { Label } from "../api";

const FORM: Record<Label, string> = {
  measured: "stamp-measured",
  allocated: "stamp-allocated",
  estimated: "stamp-estimated",
  excluded: "stamp-estimated",
};

export function Stamp({ label }: { label: Label }) {
  return (
    <span className={`stamp ${FORM[label]}`} title={`Confidence: ${label}`}>
      {label}
    </span>
  );
}

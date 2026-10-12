// The explanations are short bullets; **text** marks the facts worth noticing.
export function Bold({ text }: { text: string }) {
  return <>{text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : part))}</>;
}

export function Rich({ text }: { text: string }) {
  const lines = text.split("\n");
  if (lines.every((l) => l.startsWith("- "))) {
    return (
      <ul className="mt-2 list-disc space-y-2 pl-5">
        {lines.map((l, i) => (
          <li key={i} className="max-w-[65ch]">
            <Bold text={l.slice(2)} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p className="mt-1 max-w-[65ch]">
      <Bold text={text} />
    </p>
  );
}

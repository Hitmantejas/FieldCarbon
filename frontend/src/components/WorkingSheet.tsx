import { useEffect, useRef } from "react";
import type { Label } from "../api";
import { Stamp } from "./Stamp";

export interface Opened {
  title: string;
  shown: string;
  label: Label;
  how: string;
}

// Every figure can open its working: how it was calculated and how sure we are.
export function WorkingSheet({ opened, onClose }: { opened: Opened | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (opened && !d.open) d.showModal();
    if (!opened && d.open) d.close();
  }, [opened]);

  return (
    <dialog
      ref={ref}
      className="sheet"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="working-title"
    >
      {opened && (
        <div className="space-y-4 p-5">
          <div className="flex items-start justify-between gap-4">
            <h2 id="working-title" className="font-display text-3xl font-bold uppercase leading-none">{opened.title}</h2>
            <Stamp label={opened.label} />
          </div>
          <p className="num text-xl">{opened.shown}</p>
          <div>
            <h3 className="font-mono text-xs uppercase tracking-widest text-ink-soft">How this was worked out</h3>
            <p className="mt-1 max-w-[65ch]">{opened.how}</p>
          </div>
          <button onClick={onClose} className="min-h-11 w-full border-2 border-ink bg-ink px-4 font-mono text-sm uppercase tracking-widest text-paper">
            Close
          </button>
        </div>
      )}
    </dialog>
  );
}

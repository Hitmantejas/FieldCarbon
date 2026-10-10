import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";

export function CountUp({ to, format }: { to: number; format: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el || reduce) return;
    const run = animate(0, to, { duration: 1.2, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => (el.textContent = format(v)) });
    return () => run.stop();
  }, [to, reduce, format]);

  return (
    <>
      <span ref={ref} aria-hidden="true">{format(reduce ? to : 0)}</span>
      <span className="sr-only">{format(to)}</span>
    </>
  );
}

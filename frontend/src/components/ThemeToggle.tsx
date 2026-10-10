import { useTheme } from "../theme";

export function ThemeToggle() {
  const [theme, toggle] = useTheme();
  const dark = theme === "dark";
  return (
    <button
      role="switch"
      aria-checked={dark}
      onClick={toggle}
      className="flex min-h-11 items-center gap-2 border-2 border-ink bg-paper px-3 font-mono text-xs uppercase tracking-widest text-ink"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        {dark ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
        ) : (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" />
          </>
        )}
      </svg>
      {dark ? "Dark roll" : "Light paper"}
    </button>
  );
}

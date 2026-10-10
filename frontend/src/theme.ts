import { useCallback, useState } from "react";

type Theme = "light" | "dark";

export function useTheme(): [Theme, () => void] {
  // index.html already set data-theme before first paint; read it back rather than re-deciding.
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) ?? "light");
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("fc-theme", next);
    setTheme(next);
  }, [theme]);
  return [theme, toggle];
}

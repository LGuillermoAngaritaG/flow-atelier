import { NavLink } from "react-router-dom";
import { cn } from "@lib/cn";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { to: "/dashboard", label: "dashboard", mark: "" },
  { to: "/designer", label: "designer", mark: "" },
  { to: "/kanban", label: "kanban", mark: "" },
] as const;

export function TopBar() {
  return (
    <header
      data-testid="top-bar"
      className="sticky top-0 z-40 flex h-14 items-center gap-6 border-b border-border bg-background/90 px-6 backdrop-blur"
    >
      <NavLink to="/dashboard" className="flex items-baseline gap-3">
        <span className="font-display text-xl leading-none">
          flow-<em className="text-primary italic">atelier</em>
        </span>
      </NavLink>

      <div
        aria-hidden
        className="hidden flex-1 items-center gap-2 font-mono text-[10px] uppercase text-muted-foreground md:flex"
      >
      </div>

      <nav className="flex items-center gap-1" aria-label="primary">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-1.5 rounded-sm px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground",
                isActive && "text-foreground bg-muted",
              )
            }
          >
            <span className="text-muted-foreground">{n.mark}</span>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <ThemeToggle />
    </header>
  );
}

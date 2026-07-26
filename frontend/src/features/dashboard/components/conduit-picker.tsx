import { Link } from "react-router-dom";
import { useConduits } from "@/services/ConduitProvider";
import { ConduitRow } from "./conduit-row";

interface Props {
  selected: string;
  onSelect: (name: string) => void;
}

export function ConduitPicker({ selected, onSelect }: Props) {
  const { conduits } = useConduits();

  return (
    <div>
      <h2 className="mb-3 font-display text-panel text-foreground">
        Select a conduit
      </h2>
      {/* This list used to live in a fixed 320px ScrollArea. Sitting in the
          middle of the page, it captured the wheel: scrolling toward the run
          button moved the list instead of the page, and the page appeared not
          to respond. The list scrolls with the document now. */}
      {conduits.length === 0 ? (
        <div
          data-testid="conduit-picker"
          className="border border-border bg-card/60 py-12 text-center"
        >
          <div className="font-mono text-label uppercase tracking-[0.12em] text-muted-foreground">
            no conduits yet
          </div>
          <p className="mx-auto mt-2 max-w-[42ch] text-body leading-relaxed text-muted-foreground">
            A conduit is a saved pipeline of tasks you can run or schedule.
          </p>
          {/* Was flat text naming a destination it didn't take you to. */}
          <Link
            to="/designer"
            className="mt-4 inline-flex h-11 items-center rounded-sm border border-primary px-4 font-mono text-label uppercase tracking-[0.12em] text-primary hover:bg-primary hover:text-primary-foreground"
          >
            build one in the designer
          </Link>
        </div>
      ) : (
        <div data-testid="conduit-picker" className="border border-border bg-card/60">
          {conduits.map((c) => (
            <ConduitRow
              key={c.name}
              conduit={c}
              active={c.name === selected}
              onClick={() => onSelect(c.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

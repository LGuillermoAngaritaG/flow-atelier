import { useConduits } from "@/services/ConduitProvider";
import { ConduitRow } from "./conduit-row";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CONDUIT_PICKER_SCROLL_THRESHOLD } from "@/constants/dashboard";


interface Props {
  selected: string;
  onSelect: (name: string) => void;
}

export function ConduitPicker({ selected, onSelect }: Props) {
  const { conduits } = useConduits();
  const needsScroll = conduits.length > CONDUIT_PICKER_SCROLL_THRESHOLD;
  const list = conduits.length === 0 ? (
    <div
      data-testid="conduit-picker"
      className="border border-border bg-card/60 py-12 text-center"
    >
      <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
        no conduits yet
      </div>
      <div className="mt-2 font-mono text-[11px] text-muted-foreground/60">
        create one in the designer to get started
      </div>
    </div>
  ) : (
    <div
      data-testid="conduit-picker"
      className="border border-border bg-card/60"
    >
      {conduits.map((c, i) => (
        <ConduitRow
          key={c.name}
          conduit={c}
          idx={i + 1}
          active={c.name === selected}
          onClick={() => onSelect(c.name)}
        />
      ))}
    </div>
  );

  return (
    <div>
      <h2 className="sub-title">
        · select conduit
      </h2>
      {needsScroll ? (
        <ScrollArea className="h-[320px]">{list}</ScrollArea>
      ) : (
        list
      )}
    </div>
  );
}

import { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useConduits, getConduitSync } from "@/services/ConduitProvider";
import { createConduit, updateConduit } from "@/services/api/conduits";
import {
  loadDraftConduit,
  saveDraftConduit,
  clearDraftConduit,
} from "@/services/storage/draft-conduit";
import type { Conduit, ConduitTask } from "@/types/conduit";
import { escapeRegExp } from "@/utils/regex";
import { Canvas } from "./components/Canvas";
import { ToolPanel } from "./components/ToolPanel";
import { Inspector } from "./components/Inspector";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { renderConduitYaml } from "@/utils/yaml";
import { useUndoState } from "@/hooks/useUndoState";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Menu } from "lucide-react";

function initConduit(conduits: Conduit[]): Conduit {
  return (
    loadDraftConduit() ??
    structuredClone(getConduitSync("deploy_pipeline", conduits) ?? {
      name: "new_conduit",
      description: "",
      inputs: {},
      tasks: [],
    })
  );
}

export function Designer() {
  const { conduits: allConduits } = useConduits();
  const [conduit, setConduitRaw, undo] = useUndoState<Conduit>(() => initConduit(allConduits));
  const [saving, setSaving] = useState(false);

  const setConduit = useCallback(
    (value: Conduit | ((prev: Conduit) => Conduit)) => {
      setConduitRaw((prev) => {
        const next =
          typeof value === "function"
            ? (value as (p: Conduit) => Conduit)(prev)
            : value;
        saveDraftConduit(next);
        return next;
      });
    },
    [setConduitRaw],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo]);

  const [selectedName, setSelectedName] = useState<string | undefined>();
  const [yamlOpen, setYamlOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createTimeout, setCreateTimeout] = useState("3600");
  const [createMaxConcurrency, setCreateMaxConcurrency] = useState("1");
  const positionRef = useRef<((tool: string) => { x: number; y: number }) | null>(null);
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [toolPanelOpen, setToolPanelOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const updateTask = useCallback(
    (name: string, partial: Partial<ConduitTask>) => {
      const newName = partial.name && partial.name !== name ? partial.name : null;
      setConduit((prev) => ({
        ...prev,
        tasks: prev.tasks.map((t) => {
          if (t.name === name) return { ...t, ...partial };
          if (!newName) return t;
          return {
            ...t,
            dependsOn: t.dependsOn.map((d) => (d === name ? newName : d)),
            conditionalOn: t.conditionalOn?.task === name
              ? { ...t.conditionalOn, task: newName }
              : t.conditionalOn,
          };
        }),
      }));
      if (newName) setSelectedName(newName);
    },
    [setConduit],
  );

  const deleteTask = useCallback((name: string) => {
    setConduit((prev) => ({
      ...prev,
      tasks: prev.tasks
        .filter((t) => t.name !== name)
        .map((t) => ({
          ...t,
          dependsOn: t.dependsOn.filter((d) => d !== name),
        })),
    }));
    setSelectedName((prev) => (prev === name ? undefined : prev));
  }, [setConduit]);

  const addTask = useCallback((task: ConduitTask) => {
    const pos = positionRef.current?.(task.tool) ?? task.position ?? { x: 80, y: 140 };
    setConduit((prev) => {
      // Generate a unique temp name if empty to avoid id collisions in ReactFlow
      const name = task.name || (() => {
        const existing = new Set(prev.tasks.map((t) => t.name));
        let n = 1;
        while (existing.has(`task_${n}`)) n++;
        return `task_${n}`;
      })();
      const positioned = { ...task, name, position: pos };
      setSelectedName(name);
      return {
        ...prev,
        tasks: [...prev.tasks, positioned],
      };
    });
  }, [setConduit]);

  const addInput = useCallback(
    (name: string, hint: string) => {
      setConduit((prev) => ({
        ...prev,
        inputs: { ...prev.inputs, [name]: hint },
      }));
    },
    [setConduit],
  );

  const removeInput = useCallback(
    (name: string) => {
      const ref = `{{inputs.${name}}}`;
      const esc = escapeRegExp(name);
      const refRe = new RegExp(`\\$\\{inputs\\.${esc}\\}|\\{\\{inputs\\.${esc}\\}\\}`, "g");
      setConduit((prev) => {
        const { [name]: _, ...rest } = prev.inputs;
        return {
          ...prev,
          inputs: rest,
          tasks: prev.tasks.map((t) => ({
            ...t,
            task: t.task.replaceAll(ref, ""),
            ...(t.inputs
              ? {
                  inputs: Object.fromEntries(
                    Object.entries(t.inputs).map(([k, v]) => [k, v.replaceAll(refRe, "")]),
                  ),
                }
              : {}),
          })),
        };
      });
    },
    [setConduit],
  );

  const selectedTask = conduit.tasks.find((t) => t.name === selectedName);

  const handleSelect = useCallback(
    (task: ConduitTask | undefined) => setSelectedName(task?.name),
    [],
  );

  const handleSelectConduit = useCallback((name: string) => {
    const c = getConduitSync(name, allConduits);
    if (c) {
      setConduit(structuredClone(c));
      setSelectedName(undefined);
    }
  }, [setConduit, allConduits]);

  const handlePickerSelect = useCallback((name: string) => {
    handleSelectConduit(name);
    setPickerOpen(false);
  }, [handleSelectConduit]);

  const handleShowTools = useCallback(() => {
    setSelectedName(undefined);
  }, []);

  const handleCreate = () => {
    const name = createName.trim();
    if (!name) return;
    const timeout = Number(createTimeout) || undefined;
    const maxConcurrency = Number(createMaxConcurrency) || undefined;
    const draft: Conduit = {
      name,
      description: createDesc.trim(),
      timeout,
      maxConcurrency,
      runPath: "",
      inputs: {},
      tasks: [],
    };
    setConduit(draft);
    setCreateOpen(false);
    setCreateName("");
    setCreateDesc("");
    setCreateTimeout("3600");
    setCreateMaxConcurrency("1");
  };

  const canSave =
    conduit.name.trim() !== "" &&
    conduit.description.trim() !== "" &&
    conduit.tasks.length > 0;

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      name: conduit.name,
      description: conduit.description,
      inputs: conduit.inputs,
      timeout: conduit.timeout,
      maxConcurrency: conduit.maxConcurrency,
      tasks: conduit.tasks,
    };
    const isExisting = allConduits.some((c) => c.name === conduit.name);
    try {
      if (isExisting) {
        await updateConduit(payload);
      } else {
        await createConduit(payload);
      }
      clearDraftConduit();
      toast.success(`Saved conduit ${conduit.name}`);
      setTimeout(() => navigate("/dashboard"), 350);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save conduit");
    } finally {
      setSaving(false);
    }
  };

  const handleInspect = useCallback(
    (task: ConduitTask) => {
      setSelectedName(task.name);
      if (isMobile) setInspectorOpen(true);
    },
    [isMobile],
  );

  return (
    <div
      data-route="designer"
      className="flex h-[calc(100vh-3.5rem)] w-full border-b border-border lg:h-[calc(100vh-3.5rem-1.75rem)]"
    >
      <section className="relative flex-1">
        <Canvas
          conduit={conduit}
          onSelect={handleSelect}
          onInspect={handleInspect}
          onUpdateTask={updateTask}
          onDeleteTask={deleteTask}
          onShowTools={handleShowTools}
          positionRef={positionRef}
        />

        {/* Desktop: inline action buttons */}
        <div
          data-testid="designer-actions"
          className="pointer-events-none absolute inset-x-0 top-4 z-10 hidden justify-center lg:flex"
        >
          <div className="pointer-events-auto flex gap-2 rounded-sm border border-border bg-card/80 px-2 py-1 backdrop-blur">
            <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm" data-testid="open-conduit">
                  open conduit
                </Button>
              </DialogTrigger>
              <OpenConduitDialogContent
                allConduits={allConduits}
                currentName={conduit.name}
                onSelect={handlePickerSelect}
              />
            </Dialog>

            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm" data-testid="new-conduit">
                  new conduit
                </Button>
              </DialogTrigger>
              <CreateConduitDialogContent
                name={createName}
                setName={setCreateName}
                desc={createDesc}
                setDesc={setCreateDesc}
                timeout={createTimeout}
                setTimeout={setCreateTimeout}
                maxConcurrency={createMaxConcurrency}
                setMaxConcurrency={setCreateMaxConcurrency}
                onCreate={handleCreate}
              />
            </Dialog>

            <Sheet open={yamlOpen} onOpenChange={setYamlOpen}>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" data-testid="preview-yaml">
                  preview yaml
                </Button>
              </SheetTrigger>
              <PreviewYamlSheetContent conduit={conduit} />
            </Sheet>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!canSave || saving}
              data-testid="designer-save"
            >
              ▸ save conduit
            </Button>
          </div>
        </div>

        {/* Mobile: burger menu at top-left */}
        <div className="absolute left-3 top-3 z-10 lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="rounded-sm border border-border bg-card/90 p-2 backdrop-blur hover:bg-muted"
          >
            <Menu className="size-4 text-foreground" />
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <div className="absolute left-0 top-full z-50 mt-1 flex min-w-[160px] flex-col gap-1 rounded-sm border border-border bg-card p-2 shadow-md">
                <Dialog open={pickerOpen} onOpenChange={(open) => { setPickerOpen(open); if (!open) setMenuOpen(false); }}>
                  <DialogTrigger asChild>
                    <button type="button" className="w-full rounded-sm px-3 py-2 text-left font-mono text-[11px] text-foreground hover:bg-muted">
                      open conduit
                    </button>
                  </DialogTrigger>
                  <OpenConduitDialogContent
                    allConduits={allConduits}
                    currentName={conduit.name}
                    onSelect={(name) => { handlePickerSelect(name); setMenuOpen(false); }}
                  />
                </Dialog>

                <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) setMenuOpen(false); }}>
                  <DialogTrigger asChild>
                    <button type="button" className="w-full rounded-sm px-3 py-2 text-left font-mono text-[11px] text-foreground hover:bg-muted">
                      new conduit
                    </button>
                  </DialogTrigger>
                  <CreateConduitDialogContent
                    name={createName}
                    setName={setCreateName}
                    desc={createDesc}
                    setDesc={setCreateDesc}
                    timeout={createTimeout}
                    setTimeout={setCreateTimeout}
                    maxConcurrency={createMaxConcurrency}
                    setMaxConcurrency={setCreateMaxConcurrency}
                    onCreate={handleCreate}
                  />
                </Dialog>

                <Sheet open={yamlOpen} onOpenChange={(open) => { setYamlOpen(open); if (!open) setMenuOpen(false); }}>
                  <SheetTrigger asChild>
                    <button type="button" className="w-full rounded-sm px-3 py-2 text-left font-mono text-[11px] text-foreground hover:bg-muted">
                      preview yaml
                    </button>
                  </SheetTrigger>
                  <PreviewYamlSheetContent conduit={conduit} />
                </Sheet>

                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); handleSave(); }}
                  disabled={!canSave || saving}
                  className="w-full rounded-sm px-3 py-2 text-left font-mono text-[11px] text-primary hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
                >
                  ▸ save conduit
                </button>
              </div>
            </>
          )}
        </div>
      </section>

      {/* Desktop: inline sidebars */}
      {!isMobile && (
        selectedTask ? (
          <aside className="w-[304px] shrink-0 overflow-auto border-l border-border">
            <Inspector task={selectedTask} conduit={conduit} conduits={allConduits} onUpdateTask={updateTask} conduitInputs={conduit.inputs} onAddInput={addInput} />
          </aside>
        ) : (
          <aside className="w-[280px] shrink-0 overflow-auto border-l border-border">
            <ToolPanel conduit={conduit} conduitInputs={conduit.inputs} onAddTask={addTask} onAddInput={addInput} onRemoveInput={removeInput} />
          </aside>
        )
      )}

      {/* Mobile: tool panel sheet — full screen from right */}
      <Sheet open={toolPanelOpen} onOpenChange={setToolPanelOpen}>
        <SheetContent side="right" className="w-full overflow-auto sm:max-w-full">
          <SheetHeader>
            <SheetTitle>tools</SheetTitle>
          </SheetHeader>
          <ToolPanel conduit={conduit} conduitInputs={conduit.inputs} onAddTask={(task) => { addTask(task); setToolPanelOpen(false); }} onAddInput={addInput} onRemoveInput={removeInput} />
        </SheetContent>
      </Sheet>

      {/* Mobile: inspector sheet — full screen from right */}
      <Sheet open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <SheetContent side="right" className="w-full overflow-auto sm:max-w-full">
          <SheetHeader>
            <SheetTitle>inspector</SheetTitle>
          </SheetHeader>
          {selectedTask && (
            <Inspector task={selectedTask} conduit={conduit} conduits={allConduits} onUpdateTask={updateTask} conduitInputs={conduit.inputs} onAddInput={addInput} />
          )}
        </SheetContent>
      </Sheet>

      {/* Mobile: floating tools tab */}
      {isMobile && (
        <button
          type="button"
          onClick={() => setToolPanelOpen(true)}
          className="fixed right-0 top-1/2 z-20 -translate-y-1/2 rounded-l-md border border-r-0 border-border bg-card/90 px-2 py-3 text-[10px] font-mono uppercase tracking-[0.1em] text-foreground shadow-sm backdrop-blur hover:bg-muted"
        >
          tools
        </button>
      )}
    </div>
  );
}

// Shared dialog/sheet bodies, used by both the desktop toolbar and the mobile
// burger menu so the two never drift out of sync.

function OpenConduitDialogContent({
  allConduits,
  currentName,
  onSelect,
}: {
  allConduits: Conduit[];
  currentName: string;
  onSelect: (name: string) => void;
}) {
  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>
          Open a <em className="text-primary not-italic">conduit</em>
        </DialogTitle>
        <DialogDescription>
          Select an existing conduit to edit in the designer.
        </DialogDescription>
      </DialogHeader>
      <div className="max-h-[360px] overflow-auto">
        <div className="flex flex-col gap-1.5">
          {allConduits.map((c) => (
            <button
              key={c.name}
              type="button"
              onClick={() => onSelect(c.name)}
              className={`w-full rounded-md border px-3 py-2.5 text-left transition-colors ${
                c.name === currentName
                  ? "border-primary/50 bg-primary/8"
                  : "border-border/50 hover:border-border hover:bg-muted/40"
              }`}
            >
              <div
                className={`font-mono text-[11px] leading-tight ${
                  c.name === currentName ? "text-primary" : "text-foreground"
                }`}
              >
                {c.name}
              </div>
              {c.description && (
                <div className="mt-1 truncate text-[10px] leading-snug text-muted-foreground">
                  {c.description}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="outline" size="sm">cancel</Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  );
}

function CreateConduitDialogContent({
  name,
  setName,
  desc,
  setDesc,
  timeout,
  setTimeout,
  maxConcurrency,
  setMaxConcurrency,
  onCreate,
}: {
  name: string;
  setName: (v: string) => void;
  desc: string;
  setDesc: (v: string) => void;
  timeout: string;
  setTimeout: (v: string) => void;
  maxConcurrency: string;
  setMaxConcurrency: (v: string) => void;
  onCreate: () => void;
}) {
  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>
          Create a new <em className="text-primary not-italic">conduit</em>
        </DialogTitle>
        <DialogDescription>
          Name and describe the conduit. Add tasks in the canvas, then save when ready.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 py-2">
        <div className="grid gap-2">
          <Label htmlFor="conduit-name">name</Label>
          <Input
            id="conduit-name"
            placeholder="e.g. my_pipeline"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onCreate();
            }}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="conduit-desc">description</Label>
          <Input
            id="conduit-desc"
            placeholder="What this conduit does"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onCreate();
            }}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label htmlFor="conduit-timeout">timeout (seconds)</Label>
            <Input
              id="conduit-timeout"
              type="number"
              min={1}
              placeholder="3600"
              value={timeout}
              onChange={(e) => setTimeout(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="conduit-max-concurrency">max concurrency</Label>
            <Input
              id="conduit-max-concurrency"
              type="number"
              min={1}
              placeholder="1"
              value={maxConcurrency}
              onChange={(e) => setMaxConcurrency(e.target.value)}
            />
          </div>
        </div>
      </div>
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="outline" size="sm">cancel</Button>
        </DialogClose>
        <Button size="sm" onClick={onCreate} data-testid="create-conduit-submit">
          create
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

function PreviewYamlSheetContent({ conduit }: { conduit: Conduit }) {
  return (
    <SheetContent
      side="right"
      className="flex w-full flex-col sm:max-w-[560px]"
      data-testid="yaml-sheet"
    >
      <SheetHeader>
        <SheetTitle>
          <em className="text-primary not-italic">preview</em> yaml
        </SheetTitle>
        <SheetDescription>
          read-only · rendered from current canvas state
        </SheetDescription>
      </SheetHeader>
      <ScrollArea className="flex-1 px-6 py-4">
        <pre
          data-testid="yaml-contents"
          className="whitespace-pre font-mono text-[11px] leading-relaxed text-foreground"
        >
          {renderConduitYaml(conduit)}
        </pre>
      </ScrollArea>
    </SheetContent>
  );
}

export function CanvasRulers() {
  return (
    <div
      aria-hidden
      data-testid="canvas-rulers"
      className="pointer-events-none absolute inset-0 z-[1]"
    >
      <div
        className="absolute inset-0 opacity-50"
        style={{
          backgroundImage:
            "radial-gradient(circle, oklch(0.28 0.01 60) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
    </div>
  );
}

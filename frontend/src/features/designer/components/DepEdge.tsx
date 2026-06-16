import { useContext } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { EdgePopupContext } from "../edge-popup-context";
import type { EdgeKind } from "./EdgeTypePopup";

export interface DepEdgeData extends Record<string, unknown> {
  conditional?: "match" | "not_match";
  edgeKind?: EdgeKind;
}

function kindToLabel(kind?: EdgeKind): string {
  switch (kind) {
    case "match":
      return "match";
    case "not_match":
      return "not match";
    default:
      return "depends on";
  }
}

export function DepEdge(props: EdgeProps) {
  const {
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerEnd,
    data,
    source,
    target,
  } = props;
  const d = (data ?? {}) as DepEdgeData;
  const showPopup = useContext(EdgePopupContext);

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const color = d.conditional
    ? d.conditional === "match"
      ? "var(--color-primary)"
      : "var(--color-destructive)"
    : "black";

  return (
    <>
      <BaseEdge
        id={props.id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={20}
        style={{
          stroke: color,
          strokeWidth: 3,
          strokeDasharray: d.conditional ? "6 4" : undefined,
          fill: "none",
        }}
      />
      <EdgeLabelRenderer>
        {d.edgeKind !== "depends_on" && (
          <div
            data-testid="edge-label"
            data-conditional={d.conditional ?? undefined}
            onClick={(e) => {
              e.stopPropagation();
              showPopup({
                source,
                target,
                x: e.clientX,
                y: e.clientY,
                current: d.edgeKind,
              });
            }}
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              background: "var(--color-background)",
              border: `1px solid ${color}`,
              color,
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              padding: "2px 6px",
              pointerEvents: "all",
              cursor: "pointer",
            }}
          >
            {kindToLabel(d.edgeKind)}
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  );
}

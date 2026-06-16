import { createContext } from "react";
import type { EdgeKind } from "./components/EdgeTypePopup";

export interface PopupInfo {
  source: string;
  target: string;
  x: number;
  y: number;
  current?: EdgeKind;
  isNew?: boolean;
}

export const EdgePopupContext = createContext<(info: PopupInfo) => void>(() => {});

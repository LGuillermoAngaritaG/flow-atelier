export type LogLevel = "info" | "ok" | "err" | "acc";

export interface CannedLine {
  text: string;
  level: LogLevel;
}

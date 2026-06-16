export interface PriorFlow {
  flowId: string;
  conduitName: string;
  startedAt: number;
  finishedAt?: number;
  duration?: number;
  status: "done" | "failed" | "cancelled";
  author?: string;
}

import type { components } from "../../api/generated/schema";

export type ObservationStatus = components["schemas"]["ObservationResponse"]["status"];

export const OBSERVATION_STATUS_META: Record<
  ObservationStatus,
  { label: string; className: string; needsAction: boolean }
> = {
  uploaded: { label: "待整理", className: "bg-stone-100 text-stone-600", needsAction: false },
  processing: { label: "整理中…", className: "bg-blue-50 text-blue-700", needsAction: false },
  ready_for_review: { label: "待确认", className: "bg-orange-100 font-bold text-orange-700", needsAction: true },
  confirmed: { label: "已完成", className: "bg-emerald-50 text-emerald-700", needsAction: false },
  failed: { label: "处理失败", className: "bg-red-50 text-red-700", needsAction: true },
};

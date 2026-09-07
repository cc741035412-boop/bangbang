import { ChevronRight, Play } from "lucide-react";
import { Link } from "react-router";

import { AreaBadge } from "./area-badge";
import { MediaThumbnail } from "./media-thumbnail";
import { childAccent } from "../lib/child-colors";
import type { Media, Observation } from "../features/observations/api";
import { formatKindergartenTime } from "../lib/date-time";

const STATUS = {
  uploaded: { label: "○ 待生成记录", className: "text-amber-600" },
  processing: { label: "● 正在整理…", className: "text-blue-600" },
  ready_for_review: { label: "● 草稿未完成", className: "text-brand" },
  confirmed: { label: "✓ 已生成记录", className: "text-[#8b9994]" },
  failed: { label: "! 整理失败，点开重试", className: "text-red-700" },
} as const;

export function MaterialCard({ areaName, childName, media, record }: {
  areaName: string;
  childName: string;
  media?: Media;
  record: Observation;
}) {
  const isVideo = media?.content_type.startsWith("video/") || record.media_type === "video";
  const destination = record.status === "confirmed" ? `/observations/${record.id}` : `/observations/${record.id}/review`;
  const duration = formatDuration(media?.duration_sec ?? 0);
  const status = STATUS[record.status];
  const childColor = childAccent(record.child_id ?? 0);

  return (
    <Link aria-label={`打开${areaName}记录`} className="flex items-center gap-3 rounded-2xl border border-[#e0ddd5] bg-white p-3 text-inherit shadow-[0_1px_3px_rgba(38,45,40,0.03)]" to={destination}>
      <div className="relative size-[80px] shrink-0 overflow-hidden rounded-xl">
        <MediaThumbnail className="size-full" media={media} mediaType={record.media_type} />
        {isVideo && <span className="absolute inset-0 grid place-items-center text-white drop-shadow"><Play aria-hidden fill="currentColor" size={27} /></span>}
        {duration && <span className="absolute bottom-1 right-1 rounded bg-[#233d34]/90 px-1.5 py-0.5 text-[11px] text-white">{duration}</span>}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[16px] font-bold">{areaName} · {isVideo ? "视频" : "照片"}</p>
        <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-ink-muted">
          <span
            className="rounded-full px-2.5 py-1"
            style={{ backgroundColor: childColor.bg, color: childColor.text }}
          >
            {childName}
          </span>
          <AreaBadge name={areaName} />
          <span className="rounded-full bg-[#f0efeb] px-2.5 py-1">{formatKindergartenTime(record.created_at ?? record.observed_at)}</span>
        </div>
        <p className={`mt-2 text-sm ${status.className}`}>{status.label}</p>
      </div>
      <ChevronRight aria-hidden className="shrink-0 text-[#c5cbc8]" size={20} />
    </Link>
  );
}

function formatDuration(seconds: number) {
  if (seconds <= 0) return "";
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

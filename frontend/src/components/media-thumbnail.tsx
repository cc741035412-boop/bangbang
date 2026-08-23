import { Image as ImageIcon, Video } from "lucide-react";
import { useState } from "react";

import {
  getMediaFileUrl,
  getMediaThumbnailUrl,
  type Media,
} from "../features/observations/api";

interface MediaThumbnailProps {
  className?: string;
  media?: Media;
  mediaType?: string | null;
}

export function MediaThumbnail({ className = "", media, mediaType }: MediaThumbnailProps) {
  const [failedMediaId, setFailedMediaId] = useState<number | null>(null);
  const isVideo = media?.content_type.startsWith("video/") || mediaType === "video";
  const hasError = media?.id === failedMediaId;

  const containerClass = `grid place-items-center overflow-hidden bg-thumbnail text-brand-deep ${className}`;

  if (!media || hasError) {
    return (
      <div className={containerClass}>
        {isVideo
          ? <Video aria-label="视频素材" size={28} strokeWidth={1.8} />
          : <ImageIcon aria-label="图片素材" size={28} strokeWidth={1.8} />}
      </div>
    );
  }

  return (
    <div className={containerClass}>
      <img
        alt={isVideo ? "视频缩略图" : "素材缩略图"}
        className="size-full object-cover"
        onError={() => setFailedMediaId(media.id)}
        src={isVideo ? getMediaThumbnailUrl(media.id) : getMediaFileUrl(media.id)}
      />
    </div>
  );
}

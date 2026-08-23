import { useParams } from "react-router";

import { PagePlaceholder } from "../components/page-placeholder";

export function ObservationReviewPage() {
  const { observationId } = useParams();

  return (
    <PagePlaceholder
      title="AI 整理与教师确认"
      description={`核对观察记录 #${observationId ?? "未知"} 的白描、指标、分析与措施。`}
    />
  );
}

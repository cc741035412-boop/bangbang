import { useParams } from "react-router";

import { PagePlaceholder } from "../components/page-placeholder";

export function ObservationDetailPage() {
  const { observationId } = useParams();

  return (
    <PagePlaceholder
      title="观察记录详情"
      description={`查看观察记录 #${observationId ?? "未知"} 的已确认内容。`}
    />
  );
}

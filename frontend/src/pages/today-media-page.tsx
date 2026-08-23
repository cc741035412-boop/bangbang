import { Link } from "react-router";

import { PagePlaceholder } from "../components/page-placeholder";

export function TodayMediaPage() {
  return (
    <PagePlaceholder title="今日素材" description="查看今天上传、处理中和待确认的素材。">
      <Link
        className="mt-8 inline-flex min-h-11 items-center justify-center rounded-xl bg-brand px-5 text-base font-medium text-white"
        to="/capture"
      >
        添加素材
      </Link>
    </PagePlaceholder>
  );
}

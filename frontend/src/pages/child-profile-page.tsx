import { ChevronRight, FileText, LoaderCircle } from "lucide-react";
import { Link, Navigate, useParams } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { FEATURES } from "../config/features";
import { PROFILE_DIMENSIONS, useChildProfile } from "../features/children/api";
import { PageHeader } from "./account-page";

const DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  timeZone: "Asia/Shanghai",
});

export function ChildProfilePage() {
  const { childId } = useParams();
  const id = Number(childId);
  const profile = useChildProfile(id);

  if (!FEATURES.childProfile) return <Navigate replace to="/mine" />;
  if (!Number.isInteger(id) || id <= 0) return <Navigate replace to="/mine" />;

  const data = profile.data;
  const maxCount = Math.max(
    1,
    ...PROFILE_DIMENSIONS.map((dimension) => data?.dimension_counts?.[dimension] ?? 0),
  );

  return (
    <MobilePage>
      <main className="min-h-dvh bg-[#f7f6f1] px-5 pb-16 pt-5">
        <PageHeader title="幼儿档案" />

        {profile.isLoading && (
          <p className="mt-10 flex items-center gap-2 text-sm text-ink-muted">
            <LoaderCircle className="animate-spin text-brand" size={18} />
            正在打开档案…
          </p>
        )}
        {profile.isError && (
          <p className="mt-7 rounded-xl bg-red-50 px-3 py-3 text-sm text-red-700">
            这名幼儿的档案暂时打不开，请刷新页面重试
          </p>
        )}

        {data && (
          <>
            <header className="mt-7 flex items-center gap-4">
              <div className="grid size-16 shrink-0 place-items-center rounded-full bg-[#e7f3ed] text-2xl font-bold text-brand">
                {data.name.trim().charAt(0) || "幼"}
              </div>
              <div>
                <h2 className="text-2xl font-bold">{data.name}</h2>
                <p className="mt-1 text-sm text-[#8b9994]">
                  {data.classroom_name ?? "未分班"}
                  {data.created_at && ` · 建档于 ${DATE_FORMATTER.format(new Date(data.created_at))}`}
                </p>
              </div>
            </header>

            <div className="mt-6 grid grid-cols-3 gap-3">
              <Stat label="素材" value={data.media_count} />
              <Stat label="已生成记录" value={data.record_count} />
              <Stat label="观察天数" value={data.observed_day_count} />
            </div>

            <SectionTitle hint="出现次数">观察覆盖</SectionTitle>
            <section className="rounded-2xl border border-[#dfdcd4] bg-white p-4">
              {PROFILE_DIMENSIONS.map((dimension) => {
                const count = data.dimension_counts?.[dimension] ?? 0;
                return (
                  <div className="mb-3 flex items-center gap-3" key={dimension}>
                    <span className="w-20 shrink-0 text-sm">{dimension}</span>
                    <span className="h-2 flex-1 overflow-hidden rounded bg-[#efeee9]">
                      <span
                        className="block h-full rounded bg-brand"
                        style={{ width: `${Math.round((count / maxCount) * 100)}%` }}
                      />
                    </span>
                    <span className="w-12 shrink-0 text-right text-xs text-[#8b9994]">{count} 次</span>
                  </div>
                );
              })}
              <p className="mt-3 border-t border-dashed border-[#e3dfd7] pt-3 text-xs leading-6 text-ink-muted">
                只统计这个维度被观察到几次，不代表孩子在这方面的水平。没被观察到的，多半是还没往那边看。
              </p>
            </section>

            <SectionTitle hint="最新在上">观察记录</SectionTitle>
            {data.records.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-[#dfdcd4] px-4 py-8 text-center text-sm text-ink-muted">
                还没有生成过记录
              </p>
            ) : (
              <ul className="space-y-3">
                {data.records.map((record) => (
                  <li key={record.observation_id}>
                    <Link
                      className="flex items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white p-3 text-inherit"
                      to={`/observations/${record.observation_id}`}
                    >
                      <span className="grid size-14 shrink-0 place-items-center rounded-xl bg-thumbnail text-brand">
                        <FileText size={22} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <strong className="block truncate">{record.title}</strong>
                        <span className="mt-1 flex flex-wrap gap-1.5">
                          {record.area_name && (
                            <span className="rounded bg-[#efeee9] px-2 py-0.5 text-xs text-ink-muted">
                              {record.area_name}
                            </span>
                          )}
                          {record.dimensions.map((dimension) => (
                            <span
                              className="rounded bg-[#e7f3ed] px-2 py-0.5 text-xs text-brand"
                              key={dimension}
                            >
                              {dimension}
                            </span>
                          ))}
                        </span>
                        <span className="mt-1.5 block text-xs text-[#8b9994]">
                          {record.exported ? "✓ 已导出" : "● 未导出"} ·{" "}
                          {DATE_FORMATTER.format(new Date(record.observed_at))}
                        </span>
                      </span>
                      <ChevronRight className="shrink-0 text-[#c5cbc8]" size={19} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>
    </MobilePage>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-[#dfdcd4] bg-white px-2 py-4 text-center">
      <strong className="block text-2xl text-brand">{value}</strong>
      <span className="mt-1 block text-xs text-[#8b9994]">{label}</span>
    </div>
  );
}

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-3 mt-8 flex items-center gap-2">
      <span className="h-6 w-1 rounded bg-brand" />
      <h2 className="text-xl font-bold">{children}</h2>
      {hint && <span className="ml-auto text-sm text-[#8b9994]">{hint}</span>}
    </div>
  );
}

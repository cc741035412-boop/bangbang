import { LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Navigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { FEATURES } from "../config/features";
import {
  useCreateClassroom,
  useDeleteClassroom,
  useKindergarten,
  useRenameClassroom,
  useRenameKindergarten,
  type Classroom,
} from "../features/kindergarten/api";
import { PageHeader } from "./account-page";

export function KindergartenPage() {
  const kindergarten = useKindergarten();
  const renameKindergarten = useRenameKindergarten();
  const createClassroom = useCreateClassroom();
  const [newClassroom, setNewClassroom] = useState("");
  const [editingName, setEditingName] = useState<string | null>(null);

  if (!FEATURES.kindergarten) return <Navigate replace to="/mine" />;

  const data = kindergarten.data;
  const isOwner = data?.my_role === "owner";

  return (
    <MobilePage>
      <main className="min-h-dvh bg-[#f7f6f1] px-5 pb-16 pt-5">
        <PageHeader subtitle="园所名称、班级与同园教师" title="所在园所" />

        {kindergarten.isLoading && <p className="mt-7 text-sm text-ink-muted">正在加载园所信息…</p>}
        {kindergarten.isError && (
          <p className="mt-7 rounded-xl bg-red-50 px-3 py-3 text-sm text-red-700">
            园所信息加载失败，请刷新页面重试
          </p>
        )}

        {data && (
          <>
            <SectionTitle>园所名称</SectionTitle>
            <div className="rounded-2xl border border-[#dfdcd4] bg-white p-4">
              {editingName === null ? (
                <div className="flex items-center gap-3">
                  <span className="flex-1 text-lg font-medium">{data.name}</span>
                  {isOwner && (
                    <button
                      aria-label="修改园所名称"
                      className="text-brand"
                      onClick={() => setEditingName(data.name)}
                      type="button"
                    >
                      <Pencil size={19} />
                    </button>
                  )}
                </div>
              ) : (
                <div className="flex gap-3">
                  <input
                    className="min-h-12 flex-1 rounded-xl border border-[#dfdcd4] px-3 outline-none focus:border-brand"
                    onChange={(event) => setEditingName(event.target.value)}
                    value={editingName}
                  />
                  <button
                    className="shrink-0 rounded-xl bg-brand px-4 font-bold text-white disabled:bg-[#c2cec9]"
                    disabled={!editingName.trim() || renameKindergarten.isPending}
                    onClick={() =>
                      renameKindergarten.mutate(editingName, { onSuccess: () => setEditingName(null) })
                    }
                    type="button"
                  >
                    保存
                  </button>
                </div>
              )}
            </div>

            <SectionTitle hint={`${data.classrooms.length} 个`}>班级</SectionTitle>
            <div className="space-y-3">
              {data.classrooms.map((classroom) => (
                <ClassroomRow canEdit={isOwner} classroom={classroom} key={classroom.id} />
              ))}
              {data.classrooms.length === 0 && (
                <p className="rounded-2xl border border-dashed border-[#dfdcd4] px-4 py-6 text-center text-sm text-ink-muted">
                  还没有班级
                </p>
              )}
              {isOwner && (
                <div className="flex gap-3">
                  <input
                    className="min-h-12 flex-1 rounded-xl border border-[#dfdcd4] bg-white px-3 outline-none focus:border-brand"
                    onChange={(event) => setNewClassroom(event.target.value)}
                    placeholder="新增班级，例：中一班"
                    value={newClassroom}
                  />
                  <button
                    className="flex shrink-0 items-center gap-1 rounded-xl bg-brand px-4 font-bold text-white disabled:bg-[#c2cec9]"
                    disabled={!newClassroom.trim() || createClassroom.isPending}
                    onClick={() =>
                      createClassroom.mutate(newClassroom, { onSuccess: () => setNewClassroom("") })
                    }
                    type="button"
                  >
                    {createClassroom.isPending ? (
                      <LoaderCircle className="animate-spin" size={18} />
                    ) : (
                      <Plus size={18} />
                    )}
                    添加
                  </button>
                </div>
              )}
              {createClassroom.isError && (
                <p className="text-sm text-red-700" role="alert">
                  {(createClassroom.error as Error).message}
                </p>
              )}
            </div>

            <SectionTitle hint={`${data.teachers.length} 人`}>同园教师</SectionTitle>
            <div className="space-y-3">
              {data.teachers.map((teacher) => (
                <div
                  className="flex min-h-16 items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white px-4"
                  key={teacher.id}
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[#e7f3ed] font-bold text-brand">
                    {teacher.name.trim().charAt(0) || "师"}
                  </span>
                  <span className="flex-1 font-medium">{teacher.name}</span>
                  {teacher.role === "owner" && (
                    <span className="rounded bg-[#efeee9] px-2 py-0.5 text-xs text-ink-muted">管理员</span>
                  )}
                </div>
              ))}
            </div>

            {!isOwner && (
              <p className="mt-7 rounded-2xl bg-[#efeee9] px-4 py-3 text-sm leading-6 text-ink-muted">
                只有建园的老师可以修改园所名称和班级。需要调整请联系管理员。
              </p>
            )}
          </>
        )}
      </main>
    </MobilePage>
  );
}

function ClassroomRow({ canEdit, classroom }: { canEdit: boolean; classroom: Classroom }) {
  const [name, setName] = useState<string | null>(null);
  const rename = useRenameClassroom();
  const remove = useDeleteClassroom();

  return (
    <div className="rounded-2xl border border-[#dfdcd4] bg-white px-4 py-3">
      {name === null ? (
        <div className="flex min-h-10 items-center gap-3">
          <span className="flex-1 font-medium">{classroom.name}</span>
          <span className="text-sm text-[#8b9994]">{classroom.child_count} 名</span>
          {canEdit && (
            <>
              <button aria-label={`修改 ${classroom.name}`} className="text-brand" onClick={() => setName(classroom.name)} type="button">
                <Pencil size={18} />
              </button>
              <button
                aria-label={`删除 ${classroom.name}`}
                className="text-[#b4453c] disabled:opacity-40"
                disabled={remove.isPending}
                onClick={() => remove.mutate(classroom.id)}
                type="button"
              >
                <Trash2 size={18} />
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="flex gap-3">
          <input
            className="min-h-11 flex-1 rounded-xl border border-[#dfdcd4] px-3 outline-none focus:border-brand"
            onChange={(event) => setName(event.target.value)}
            value={name}
          />
          <button className="shrink-0 px-3 text-sm text-ink-muted" onClick={() => setName(null)} type="button">
            取消
          </button>
          <button
            className="shrink-0 rounded-xl bg-brand px-4 font-bold text-white disabled:bg-[#c2cec9]"
            disabled={!name.trim() || rename.isPending}
            onClick={() => rename.mutate({ id: classroom.id, name }, { onSuccess: () => setName(null) })}
            type="button"
          >
            保存
          </button>
        </div>
      )}
      {remove.isError && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          {(remove.error as Error).message}
        </p>
      )}
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

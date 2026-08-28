import { ChevronRight, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { FEATURES } from "../config/features";
import { useCreateChild, useDeleteChild } from "../features/children/api";
import { useSettingsData } from "../features/settings/api";
import { PageHeader } from "./account-page";

export function ChildrenManagePage() {
  const { children } = useSettingsData();
  const createChild = useCreateChild();
  const [name, setName] = useState("");
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);

  if (!FEATURES.childMutation) return <Navigate replace to="/settings" />;

  return (
    <MobilePage>
      <main className="min-h-dvh bg-[#f7f6f1] px-5 pb-16 pt-5">
        <PageHeader subtitle="新增、删除，或点进档案查看" title="幼儿档案库" />

        <div className="mt-7 flex gap-3">
          <input
            className="min-h-12 flex-1 rounded-xl border border-[#dfdcd4] bg-white px-3 outline-none focus:border-brand"
            onChange={(event) => setName(event.target.value)}
            placeholder="新增幼儿姓名"
            value={name}
          />
          <button
            className="flex shrink-0 items-center gap-1 rounded-xl bg-brand px-4 font-bold text-white disabled:bg-[#c2cec9]"
            disabled={!name.trim() || createChild.isPending}
            onClick={() => createChild.mutate({ name }, { onSuccess: () => setName("") })}
            type="button"
          >
            {createChild.isPending ? <LoaderCircle className="animate-spin" size={18} /> : <Plus size={18} />}
            添加
          </button>
        </div>
        {createChild.isError && (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {(createChild.error as Error).message}
          </p>
        )}

        {children.isLoading && <p className="mt-7 text-sm text-ink-muted">正在加载幼儿信息…</p>}

        <ul className="mt-6 space-y-3">
          {(children.data ?? []).map((child) => (
            <ChildRow
              child={child}
              key={child.id}
              onCancelDelete={() => setPendingDelete(null)}
              onRequestDelete={() => setPendingDelete(child.id)}
              pendingDelete={pendingDelete === child.id}
            />
          ))}
        </ul>

        {children.isSuccess && (children.data ?? []).length === 0 && (
          <p className="mt-10 text-center text-sm text-ink-muted">还没有幼儿，先在上面添加一个</p>
        )}
      </main>
    </MobilePage>
  );
}

function ChildRow({
  child,
  onCancelDelete,
  onRequestDelete,
  pendingDelete,
}: {
  child: { id: number; name: string };
  onCancelDelete: () => void;
  onRequestDelete: () => void;
  pendingDelete: boolean;
}) {
  const deleteChild = useDeleteChild();

  return (
    <li className="rounded-2xl border border-[#dfdcd4] bg-white px-4 py-3">
      <div className="flex min-h-11 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[#e7f3ed] font-bold text-brand">
          {child.name.trim().charAt(0) || "幼"}
        </span>
        <span className="flex-1 font-medium">{child.name}</span>
        {FEATURES.childProfile && (
          <Link
            aria-label={`打开 ${child.name} 的档案`}
            className="flex items-center gap-1 text-sm text-brand"
            to={`/children/${child.id}`}
          >
            档案 <ChevronRight size={16} />
          </Link>
        )}
        <button
          aria-label={`删除 ${child.name}`}
          className="text-[#b4453c]"
          onClick={onRequestDelete}
          type="button"
        >
          <Trash2 size={18} />
        </button>
      </div>

      {/* 删除要二次确认：档案一旦删掉，名下的素材归属也就断了 */}
      {pendingDelete && (
        <div className="mt-3 rounded-xl bg-[#fdf6f5] p-3">
          <p className="text-sm leading-6 text-[#8a4b45]">
            确认删除「{child.name}」？名下还有素材或记录时会删除失败，需要先处理那些记录。
          </p>
          {deleteChild.isError && (
            <p className="mt-2 text-sm text-red-700" role="alert">
              {(deleteChild.error as Error).message}
            </p>
          )}
          <div className="mt-3 grid grid-cols-2 gap-3">
            <button
              className="min-h-11 rounded-xl bg-white font-medium text-ink-muted"
              onClick={onCancelDelete}
              type="button"
            >
              取消
            </button>
            <button
              className="min-h-11 rounded-xl bg-[#b4453c] font-bold text-white disabled:opacity-60"
              disabled={deleteChild.isPending}
              onClick={() => deleteChild.mutate(child.id, { onSuccess: onCancelDelete })}
              type="button"
            >
              确认删除
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

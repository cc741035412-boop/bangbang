import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";

import { MobilePage } from "../components/mobile-page";
import {
  type Child,
  type Teacher,
  useSettingsData,
  useUpdateChild,
  useUpdateTeacher,
} from "../features/settings/api";

export function SettingsPage() {
  const { children, teachers } = useSettingsData();

  return (
    <MobilePage>
      <main className="px-5 py-5">
        <header className="mb-7 flex items-center gap-3">
          <Link
            aria-label="返回今日素材"
            className="grid size-11 shrink-0 place-items-center rounded-full bg-surface text-ink shadow-sm"
            to="/"
          >
            <ArrowLeft size={22} />
          </Link>
          <div>
            <h1 className="text-2xl font-bold">基础信息设置</h1>
            <p className="mt-1 text-sm text-ink-muted">仅用于补全演示所需资料</p>
          </div>
        </header>

        <section aria-labelledby="children-heading">
          <h2 className="text-lg font-bold" id="children-heading">幼儿</h2>
          {children.isLoading && <p className="mt-3 text-sm text-ink-muted">正在加载幼儿信息…</p>}
          {children.isError && <p className="mt-3 text-sm text-red-700">幼儿信息加载失败，请刷新页面重试</p>}
          <div className="mt-3 space-y-4">
            {(children.data ?? []).map((child) => (
              <ChildRow
                child={child}
                key={`${child.id}:${child.name}:${child.birth_date ?? ""}:${child.gender ?? ""}`}
              />
            ))}
          </div>
        </section>

        <section aria-labelledby="teachers-heading" className="mt-9">
          <h2 className="text-lg font-bold" id="teachers-heading">教师</h2>
          {teachers.isLoading && <p className="mt-3 text-sm text-ink-muted">正在加载教师信息…</p>}
          {teachers.isError && <p className="mt-3 text-sm text-red-700">教师信息加载失败，请刷新页面重试</p>}
          <div className="mt-3 space-y-4">
            {(teachers.data ?? []).map((teacher) => (
              <TeacherRow key={`${teacher.id}:${teacher.name}`} teacher={teacher} />
            ))}
          </div>
        </section>
      </main>
    </MobilePage>
  );
}

function ChildRow({ child }: { child: Child }) {
  const update = useUpdateChild();
  const [name, setName] = useState(child.name);
  const [birthDate, setBirthDate] = useState(child.birth_date ?? "");
  const [gender, setGender] = useState<"" | "男" | "女">(child.gender ?? "");

  function save() {
    update.mutate({
      id: child.id,
      body: {
        name: name.trim(),
        birth_date: birthDate || null,
        gender: gender || null,
      },
    });
  }

  return (
    <div className="rounded-3xl bg-surface p-4 shadow-sm">
      <label className="block text-sm font-bold" htmlFor={`child-name-${child.id}`}>姓名</label>
      <input
        className="mt-2 min-h-11 w-full rounded-xl border border-stone-300 bg-white px-3"
        id={`child-name-${child.id}`}
        onChange={(event) => setName(event.target.value)}
        value={name}
      />
      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="text-sm font-bold">
          出生日期
          <input
            className="mt-2 min-h-11 w-full rounded-xl border border-stone-300 bg-white px-3 font-normal"
            onChange={(event) => setBirthDate(event.target.value)}
            type="date"
            value={birthDate}
          />
        </label>
        <label className="text-sm font-bold">
          性别
          <select
            className="mt-2 min-h-11 w-full rounded-xl border border-stone-300 bg-white px-3 font-normal"
            onChange={(event) => setGender(event.target.value as "" | "男" | "女")}
            value={gender}
          >
            <option value="">未填写</option>
            <option value="男">男</option>
            <option value="女">女</option>
          </select>
        </label>
      </div>
      <SaveRowButton
        disabled={!name.trim() || update.isPending}
        error={update.isError}
        pending={update.isPending}
        saved={update.isSuccess}
        onClick={save}
      />
    </div>
  );
}

function TeacherRow({ teacher }: { teacher: Teacher }) {
  const update = useUpdateTeacher();
  const [name, setName] = useState(teacher.name);

  return (
    <div className="rounded-3xl bg-surface p-4 shadow-sm">
      <label className="block text-sm font-bold" htmlFor={`teacher-name-${teacher.id}`}>姓名</label>
      <input
        className="mt-2 min-h-11 w-full rounded-xl border border-stone-300 bg-white px-3"
        id={`teacher-name-${teacher.id}`}
        onChange={(event) => setName(event.target.value)}
        value={name}
      />
      <SaveRowButton
        disabled={!name.trim() || update.isPending}
        error={update.isError}
        pending={update.isPending}
        saved={update.isSuccess}
        onClick={() => update.mutate({ id: teacher.id, body: { name: name.trim() } })}
      />
    </div>
  );
}

function SaveRowButton({
  disabled,
  error,
  onClick,
  pending,
  saved,
}: {
  disabled: boolean;
  error: boolean;
  onClick: () => void;
  pending: boolean;
  saved: boolean;
}) {
  return (
    <div className="mt-4 flex items-center gap-3">
      <button
        className="min-h-11 rounded-xl bg-brand px-5 font-bold text-white disabled:bg-stone-300"
        disabled={disabled}
        onClick={onClick}
        type="button"
      >
        {pending ? "保存中…" : "保存"}
      </button>
      <p aria-live="polite" className={`text-sm ${error ? "text-red-700" : "text-ink-muted"}`}>
        {error ? "保存失败，请重试" : saved ? "已保存并刷新" : ""}
      </p>
    </div>
  );
}

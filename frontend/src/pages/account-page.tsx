import { ArrowLeft, LoaderCircle, LogOut, ShieldAlert, Smartphone } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { isCode, isPhone, useChangePhone, useDeleteAccount, useLogout, useSendCode } from "../features/auth/api";
import { useAuth } from "../features/auth/auth-context-value";

const CODE_COOLDOWN_SEC = 60;

export function AccountPage() {
  const navigate = useNavigate();
  const { account, enabled } = useAuth();
  const logout = useLogout();
  const [panel, setPanel] = useState<"none" | "phone" | "delete">("none");

  if (!enabled) return <Navigate replace to="/mine" />;
  if (!account) return <Navigate replace to="/login" />;

  return (
    <MobilePage>
      <main className="min-h-dvh bg-[#f7f6f1] px-5 pb-16 pt-5">
        <PageHeader subtitle="手机号、登录状态与账号注销" title="账号与安全" />

        <section className="mt-7 space-y-3">
          <Row icon={<Smartphone className="text-brand" size={21} />} label="手机号" value={maskPhone(account.phone)} />
          <button
            className="w-full rounded-2xl border border-[#dfdcd4] bg-white px-4 py-4 text-left font-medium"
            onClick={() => setPanel(panel === "phone" ? "none" : "phone")}
            type="button"
          >
            更换手机号
          </button>
          {panel === "phone" && <ChangePhonePanel onDone={() => setPanel("none")} />}
        </section>

        <section className="mt-9 space-y-3">
          <button
            className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl border border-[#dfdcd4] bg-white font-bold text-ink-muted"
            disabled={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) })}
            type="button"
          >
            {logout.isPending ? <LoaderCircle className="animate-spin" size={19} /> : <LogOut size={19} />}
            退出登录
          </button>

          <button
            className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl border border-[#e6cfcf] bg-white font-bold text-[#b4453c]"
            onClick={() => setPanel(panel === "delete" ? "none" : "delete")}
            type="button"
          >
            <ShieldAlert size={19} />
            注销账号
          </button>
          {panel === "delete" && <DeleteAccountPanel phone={account.phone} />}
        </section>

        <p className="mt-8 rounded-2xl bg-[#efeee9] px-4 py-3 text-sm leading-6 text-ink-muted">
          注销后，你上传的素材和已生成的观察记录会一并删除，且不可恢复。
          需要留档的记录请先在「导出记录」里导出。
        </p>
      </main>
    </MobilePage>
  );
}

function ChangePhonePanel({ onDone }: { onDone: () => void }) {
  const [newPhone, setNewPhone] = useState("");
  const [code, setCode] = useState("");
  const { cooldown, requestCode, resetRequest, sendCode } = useCodeRequest();
  const changePhone = useChangePhone();
  const ready = isPhone(newPhone) && isCode(code) && !changePhone.isPending;

  return (
    <div className="rounded-2xl border border-[#dfdcd4] bg-white p-4">
      <p className="text-sm text-ink-muted">验证码会发到<strong className="text-ink">新手机号</strong>上。</p>
      <input
        className="mt-3 min-h-12 w-full rounded-xl border border-[#dfdcd4] px-3 outline-none focus:border-brand"
        inputMode="numeric"
        maxLength={11}
        onChange={(event) => {
          setNewPhone(event.target.value.replace(/\D/g, ""));
          resetRequest();
        }}
        placeholder="新手机号"
        value={newPhone}
      />
      <div className="mt-3 flex gap-3">
        <input
          className="min-h-12 flex-1 rounded-xl border border-[#dfdcd4] px-3 outline-none focus:border-brand"
          inputMode="numeric"
          maxLength={6}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
          placeholder="验证码"
          value={code}
        />
        <button
          className="shrink-0 rounded-xl border border-[#c9e2d6] px-4 text-sm font-medium text-brand disabled:border-[#e2dfd7] disabled:text-[#a8b0ac]"
          disabled={!isPhone(newPhone) || cooldown > 0 || sendCode.isPending}
          onClick={() => requestCode(newPhone)}
          type="button"
        >
          {sendCode.isPending
            ? "发送中…"
            : cooldown > 0
              ? `${cooldown} 秒后重发`
              : "获取验证码"}
        </button>
      </div>
      {cooldown > 0 && (
        <p className="mt-3 text-sm text-brand" role="status">
          验证码已发送，5 分钟内有效。
        </p>
      )}
      {sendCode.isError && (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {(sendCode.error as Error).message}
        </p>
      )}
      {changePhone.isError && (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {(changePhone.error as Error).message}
        </p>
      )}
      <button
        className="mt-4 min-h-12 w-full rounded-xl bg-brand font-bold text-white disabled:bg-[#c2cec9]"
        disabled={!ready}
        onClick={() => changePhone.mutate({ new_phone: newPhone, code }, { onSuccess: onDone })}
        type="button"
      >
        确认更换
      </button>
    </div>
  );
}

function DeleteAccountPanel({ phone }: { phone: string }) {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const { cooldown, requestCode, sendCode } = useCodeRequest();
  const deleteAccount = useDeleteAccount();
  // 两道门：验证码 + 手打「注销」两个字。这是不可逆操作，不能一键完成
  const ready = isCode(code) && confirmText.trim() === "注销" && !deleteAccount.isPending;

  return (
    <div className="rounded-2xl border border-[#e6cfcf] bg-[#fdf6f5] p-4">
      <p className="text-sm leading-6 text-[#8a4b45]">
        这一步不可撤销。请先获取验证码，再在下方输入「注销」两个字确认。
      </p>
      <div className="mt-3 flex gap-3">
        <input
          className="min-h-12 flex-1 rounded-xl border border-[#e6cfcf] bg-white px-3 outline-none"
          inputMode="numeric"
          maxLength={6}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
          placeholder="验证码"
          value={code}
        />
        <button
          className="shrink-0 rounded-xl border border-[#e6cfcf] bg-white px-4 text-sm font-medium text-[#b4453c]"
          disabled={cooldown > 0 || sendCode.isPending}
          onClick={() => requestCode(phone)}
          type="button"
        >
          {sendCode.isPending
            ? "发送中…"
            : cooldown > 0
              ? `${cooldown} 秒后重发`
              : "获取验证码"}
        </button>
      </div>
      {cooldown > 0 && (
        <p className="mt-3 text-sm text-brand" role="status">
          验证码已发送，5 分钟内有效。
        </p>
      )}
      {sendCode.isError && (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {(sendCode.error as Error).message}
        </p>
      )}
      <input
        className="mt-3 min-h-12 w-full rounded-xl border border-[#e6cfcf] bg-white px-3 outline-none"
        onChange={(event) => setConfirmText(event.target.value)}
        placeholder="输入「注销」两个字"
        value={confirmText}
      />
      {deleteAccount.isError && (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {(deleteAccount.error as Error).message}
        </p>
      )}
      <button
        className="mt-4 min-h-12 w-full rounded-xl bg-[#b4453c] font-bold text-white disabled:bg-[#dcc4c1]"
        disabled={!ready}
        onClick={() => deleteAccount.mutate(code, { onSuccess: () => navigate("/login", { replace: true }) })}
        type="button"
      >
        确认注销账号
      </button>
    </div>
  );
}

function useCodeRequest() {
  const sendCode = useSendCode();
  const [cooldown, setCooldown] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  function clearCooldown() {
    window.clearInterval(timer.current);
    setCooldown(0);
  }

  function resetRequest() {
    clearCooldown();
    sendCode.reset();
  }

  function startCooldown() {
    setCooldown(CODE_COOLDOWN_SEC);
    window.clearInterval(timer.current);
    timer.current = window.setInterval(() => {
      setCooldown((left) => {
        if (left <= 1) {
          window.clearInterval(timer.current);
          return 0;
        }
        return left - 1;
      });
    }, 1000);
  }

  function requestCode(phone: string) {
    if (!isPhone(phone) || cooldown > 0 || sendCode.isPending) return;
    sendCode.mutate(phone, { onSuccess: startCooldown });
  }

  return { cooldown, requestCode, resetRequest, sendCode };
}

export function PageHeader({ subtitle, title }: { subtitle?: string; title: string }) {
  return (
    <header className="flex items-center gap-3">
      <Link
        aria-label="返回"
        className="grid size-11 shrink-0 place-items-center rounded-full bg-surface text-ink shadow-sm"
        to="/mine"
      >
        <ArrowLeft size={22} />
      </Link>
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
    </header>
  );
}

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex min-h-16 items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white px-4">
      {icon}
      <span className="flex-1 font-medium">{label}</span>
      <span className="text-sm text-[#8b9994]">{value}</span>
    </div>
  );
}

function maskPhone(phone: string) {
  return phone.length === 11 ? `${phone.slice(0, 3)}****${phone.slice(7)}` : phone;
}

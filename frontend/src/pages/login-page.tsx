import { LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { isCode, isPhone, useLogin, useRegister, useSendCode } from "../features/auth/api";
import { useAuth } from "../features/auth/auth-context-value";

type Mode = "login" | "register";

const CODE_COOLDOWN_SEC = 60;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { account, enabled } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [kindergarten, setKindergarten] = useState("");
  const [classroom, setClassroom] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  const sendCode = useSendCode();
  const login = useLogin();
  const register = useRegister();
  const pending = login.isPending || register.isPending;
  const backTo = (location.state as { from?: string } | null)?.from ?? "/";

  useEffect(() => () => window.clearInterval(timer.current), []);

  // 登录能力没接后端时不展示本页，避免出现一个走不通的入口
  if (!enabled) return <Navigate replace to="/" />;
  if (account) return <Navigate replace to={backTo} />;

  const isRegister = mode === "register";
  const registerFilled = Boolean(name.trim() && kindergarten.trim() && classroom.trim());
  const canSubmit =
    isPhone(phone) && isCode(code) && agreed && (!isRegister || registerFilled) && !pending;

  function startCooldown() {
    setCooldown(CODE_COOLDOWN_SEC);
    window.clearInterval(timer.current);
    timer.current = window.setInterval(() => {
      setCooldown((left) => {
        if (left <= 1) window.clearInterval(timer.current);
        return left - 1;
      });
    }, 1000);
  }

  function requestCode() {
    if (!isPhone(phone) || cooldown > 0 || sendCode.isPending) return;
    sendCode.mutate(phone, { onSuccess: startCooldown });
  }

  function submit() {
    if (!canSubmit) return;
    const done = { onSuccess: () => navigate(backTo, { replace: true }) };
    if (isRegister) {
      register.mutate(
        { phone, code, name, kindergarten_name: kindergarten, classroom_name: classroom },
        done,
      );
    } else {
      login.mutate({ phone, code }, done);
    }
  }

  const error =
    (login.error ?? register.error ?? sendCode.error) instanceof Error
      ? (login.error ?? register.error ?? sendCode.error)!.message
      : "";

  return (
    <MobilePage>
      <main className="flex min-h-dvh flex-col bg-[#f7f6f1] px-7 pb-10 pt-16">
        <h1 className="text-[32px] font-bold tracking-tight">帮帮师记</h1>
        <p className="mt-2 text-base leading-7 text-ink-muted">
          {isRegister
            ? "填好这几项，生成的记录会直接带上你的落款。"
            : "拍完就传，记录当天写完。"}
        </p>

        <form
          className="mt-9 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <Field label="手机号">
            <input
              autoComplete="tel"
              className={inputClass}
              inputMode="numeric"
              maxLength={11}
              onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
              placeholder="请输入手机号"
              value={phone}
            />
          </Field>

          <Field label="验证码">
            <div className="flex gap-3">
              <input
                autoComplete="one-time-code"
                className={`${inputClass} flex-1`}
                inputMode="numeric"
                maxLength={6}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                placeholder="6 位验证码"
                value={code}
              />
              <button
                className="shrink-0 rounded-xl border border-[#c9e2d6] bg-white px-4 text-sm font-medium text-brand disabled:border-[#e2dfd7] disabled:text-[#a8b0ac]"
                disabled={!isPhone(phone) || cooldown > 0 || sendCode.isPending}
                onClick={requestCode}
                type="button"
              >
                {cooldown > 0 ? `${cooldown} 秒后重发` : "获取验证码"}
              </button>
            </div>
          </Field>

          {isRegister && (
            <>
              <Field label="姓名">
                <input
                  className={inputClass}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例：李老师"
                  value={name}
                />
              </Field>
              <Field label="所在园所">
                <input
                  className={inputClass}
                  onChange={(event) => setKindergarten(event.target.value)}
                  placeholder="例：阳光第一幼儿园"
                  value={kindergarten}
                />
              </Field>
              <Field label="带班">
                <input
                  className={inputClass}
                  onChange={(event) => setClassroom(event.target.value)}
                  placeholder="例：中一班"
                  value={classroom}
                />
              </Field>
            </>
          )}

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}

          <button
            className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-brand text-lg font-bold text-white disabled:bg-[#c2cec9]"
            disabled={!canSubmit}
            type="submit"
          >
            {pending && <LoaderCircle className="animate-spin" size={19} />}
            {isRegister ? "注册并登录" : "登录"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-ink-muted">
          {isRegister ? "已经有账号了？" : "第一次用？"}
          <button
            className="ml-1 font-bold text-brand"
            onClick={() => setMode(isRegister ? "login" : "register")}
            type="button"
          >
            {isRegister ? "去登录" : "注册新账号"}
          </button>
        </p>

        <label className="mt-6 flex items-start gap-3 text-xs leading-6 text-ink-muted">
          <input
            checked={agreed}
            className="mt-1 size-4 accent-[#31745a]"
            onChange={(event) => setAgreed(event.target.checked)}
            type="checkbox"
          />
          <span>
            我已阅读并同意《用户协议》和《隐私政策》。幼儿影像仅用于生成本园观察记录。
          </span>
        </label>
      </main>
    </MobilePage>
  );
}

const inputClass =
  "min-h-13 w-full rounded-xl border border-[#dfdcd4] bg-white px-3 py-3 text-base outline-none focus:border-brand";

function Field({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm text-ink-muted">{label}</span>
      {children}
    </label>
  );
}

import { Check, Download, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

/** 监听浏览器提供的安装提示；没有提示时给出不同终端的添加主屏幕指引。 */
export function PwaInstallCard() {
  const [installEvent, setInstallEvent] = useState<InstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    function onPrompt(event: Event) {
      event.preventDefault();
      setInstallEvent(event as InstallPromptEvent);
    }
    function onInstalled() {
      setInstalled(true);
      setInstallEvent(null);
    }
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  async function install() {
    if (!installEvent) return;
    await installEvent.prompt();
    const choice = await installEvent.userChoice;
    if (choice.outcome === "accepted") setInstalled(true);
    setInstallEvent(null);
  }

  if (installed) {
    return (
      <section
        aria-label="安装体验版"
        className="rounded-2xl border border-[#cfe3d6] bg-[#eef6f1] px-4 py-4"
      >
        <div className="flex items-center gap-2 font-bold text-brand-deep">
          <Check aria-hidden size={19} />
          已经安装到主屏幕
        </div>
        <p className="mt-1 text-sm text-ink-muted">下次从主屏幕图标直接打开，就像用 App 一样。</p>
      </section>
    );
  }

  return (
    <section
      aria-label="安装体验版"
      className="rounded-2xl border border-[#dfdcd4] bg-white px-4 py-4"
    >
      <div className="flex items-center gap-2 font-bold">
        <Smartphone aria-hidden className="text-brand" size={19} />
        安装体验版
      </div>
      <p className="mt-1 text-sm leading-6 text-ink-muted">
        把它"装"到手机桌面，随时随地快速记录，无需每次打开浏览器。
      </p>

      {installEvent ? (
        <button
          className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-brand font-bold text-white"
          onClick={() => void install()}
          type="button"
        >
          <Download aria-hidden size={18} />
          安装到主屏幕
        </button>
      ) : (
        <ul className="mt-3 space-y-1.5 text-sm leading-6 text-ink-muted">
          <li>iPhone/Safari：点底部「分享」→「添加到主屏幕」</li>
          <li>安卓/Chrome：右上角菜单 →「安装应用」</li>
          <li>电脑浏览器：地址栏右侧的安装图标</li>
        </ul>
      )}
    </section>
  );
}

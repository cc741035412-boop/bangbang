import type { PropsWithChildren } from "react";

export function MobilePage({ children }: PropsWithChildren) {
  return (
    <main className="mx-auto min-h-dvh w-full max-w-[430px] bg-canvas text-ink shadow-[0_0_40px_rgba(34,40,35,0.08)]">
      {children}
    </main>
  );
}

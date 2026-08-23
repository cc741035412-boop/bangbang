import type { ReactNode } from "react";

type PagePlaceholderProps = {
  title: string;
  description: string;
  children?: ReactNode;
};

export function PagePlaceholder({ title, description, children }: PagePlaceholderProps) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-surface px-5 py-8 text-ink shadow-sm">
      <p className="text-sm font-medium text-brand">帮帮师记</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-3 text-base leading-7 text-ink-muted">{description}</p>
      {children}
    </main>
  );
}

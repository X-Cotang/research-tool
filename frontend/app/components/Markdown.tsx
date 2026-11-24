import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Terminal } from "lucide-react";

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const lang = match ? match[1] : "";
  const codeString = String(children).replace(/\n$/, "");

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="group my-3 overflow-hidden rounded-md border border-[var(--desk-border)] bg-[#050507]">
      <div className="flex items-center justify-between border-b border-[var(--desk-border-subtle)] bg-[#0d0d11] px-3 py-1.5 text-xs text-[var(--desk-ink-muted)]">
        <div className="flex items-center gap-1.5 font-mono text-[11px]">
          <Terminal className="h-3 w-3 text-[var(--desk-ink-faint)]" />
          <span className="text-[var(--desk-ink-faint)] uppercase">{lang || "code"}</span>
        </div>
        <button
          type="button"
          onClick={() => void onCopy()}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-mono text-[var(--desk-ink-muted)] transition-colors hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-[var(--desk-success)]" />
              <span className="text-[var(--desk-success)]">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-xs leading-relaxed text-[#e4e4e7]">
        <code>{children}</code>
      </pre>
    </div>
  );
}

const components: Components = {
  h1: ({ ...p }) => (
    <h1
      className="mt-4 mb-2 font-display text-base font-semibold tracking-tight text-[var(--desk-ink)]"
      {...p}
    />
  ),
  h2: ({ ...p }) => (
    <h2
      className="mt-3 mb-1.5 font-display text-sm font-semibold tracking-tight text-[var(--desk-ink)]"
      {...p}
    />
  ),
  h3: ({ ...p }) => (
    <h3
      className="mt-2.5 mb-1 font-display text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]"
      {...p}
    />
  ),
  p: ({ ...p }) => <p className="mb-2 leading-relaxed last:mb-0" {...p} />,
  ul: ({ ...p }) => (
    <ul className="my-2 list-disc space-y-1 pl-4 text-xs leading-relaxed" {...p} />
  ),
  ol: ({ ...p }) => (
    <ol className="my-2 list-decimal space-y-1 pl-4 text-xs leading-relaxed" {...p} />
  ),
  li: ({ ...p }) => <li className="pl-0.5" {...p} />,
  strong: ({ ...p }) => (
    <strong className="font-semibold text-[var(--desk-ink)]" {...p} />
  ),
  a: ({ ...p }) => (
    <a
      className="font-medium text-[var(--desk-accent)] underline underline-offset-4 hover:opacity-80"
      target="_blank"
      rel="noreferrer"
      {...p}
    />
  ),
  hr: () => <hr className="my-3 border-[var(--desk-border)]" />,
  blockquote: ({ ...p }) => (
    <blockquote
      className="my-2 border-l-2 border-[var(--desk-border-accent)] pl-3 text-xs italic text-[var(--desk-ink-muted)]"
      {...p}
    />
  ),
  code: ({ className, children, ...rest }) => {
    const isBlock = Boolean(className && /language-/.test(className));
    if (isBlock) {
      return <CodeBlock className={className}>{children}</CodeBlock>;
    }
    return (
      <code
        className="rounded border border-[var(--desk-border)] bg-[var(--desk-surface-2)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--desk-ink)]"
        {...rest}
      >
        {children}
      </code>
    );
  },
  pre: ({ children }) => <>{children}</>,
  table: ({ ...p }) => (
    <div className="my-3 overflow-x-auto rounded border border-[var(--desk-border)]">
      <table className="w-full border-collapse font-sans text-xs" {...p} />
    </div>
  ),
  th: ({ ...p }) => (
    <th
      className="border-b border-[var(--desk-border)] bg-[var(--desk-surface-2)] px-2.5 py-1.5 text-left font-mono text-[11px] font-semibold text-[var(--desk-ink-muted)] uppercase tracking-wider"
      {...p}
    />
  ),
  td: ({ ...p }) => (
    <td
      className="border-b border-[var(--desk-border-subtle)] px-2.5 py-1.5 align-top text-xs"
      {...p}
    />
  ),
};

export function Markdown({ content }: { content: string }) {
  if (!content) return null;
  return (
    <div className="min-w-0 space-y-1 text-sm text-[var(--desk-ink)]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

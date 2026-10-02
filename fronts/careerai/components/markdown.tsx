import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

type Components = React.ComponentProps<typeof ReactMarkdown>["components"]

// Prose inside cards: agent analysis, chat replies.
export const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
}

// Whole documents with headings and links: the resume and side-project ideas.
export const documentComponents: Components = {
  ...markdownComponents,
  h1: ({ children }) => <h1 className="mb-1 text-2xl font-semibold tracking-tight">{children}</h1>,
  h2: ({ children }) => (
    <h2 className="mt-6 mb-2 border-b pb-1 text-xs font-semibold uppercase tracking-wider text-brand-teal first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => <h3 className="mt-4 mb-1 font-semibold text-foreground">{children}</h3>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-brand-teal underline-offset-2 hover:underline">
      {children}
    </a>
  ),
  hr: () => <hr className="my-6 border-border" />,
  code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>,
}

// GitHub-flavored Markdown with the app's styles; "document" adds headings, links and rules.
export function Markdown({ children, variant = "prose" }: { children: string; variant?: "prose" | "document" }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={variant === "document" ? documentComponents : markdownComponents}
    >
      {children}
    </ReactMarkdown>
  )
}

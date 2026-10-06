import fs from "node:fs/promises"
import path from "node:path"

import { useEffect, useState } from "react"
import type { GetStaticProps, InferGetStaticPropsType } from "next"
import Link from "next/link"
import { useRouter } from "next/router"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { BookOpen, LoaderCircle } from "lucide-react"

import { cn } from "@/lib/utils"

const DOCS_DIR = "Documentation"

type DocHeading = {
  id: string
  text: string
}

type DocTopic = {
  slug: string
  title: string
  file: string
  headings: DocHeading[]
}

// Turns heading text into a URL-safe anchor id ("Getting Started" -> "getting-started").
function slugify(text: string) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
}

// Reads public/Documentation at build time (every request in dev) to build the sidebar.
// Files are sorted by name, so prefix them ("01-Introduction.md") to control the order.
export const getStaticProps = (async () => {
  const dir = path.join(process.cwd(), "public", DOCS_DIR)
  const files = (await fs.readdir(dir)).filter((f) => f.endsWith(".md")).sort()

  const topics = await Promise.all(
    files.map(async (file) => {
      const source = await fs.readFile(path.join(dir, file), "utf8")
      const name = file.replace(/\.md$/, "").replace(/^\d+[-_ ]*/, "")
      const h1 = source.match(/^#\s+(.+)$/m)?.[1].trim()
      const headings = [...source.matchAll(/^##\s+(.+)$/gm)].map((m) => ({
        id: slugify(m[1]),
        text: m[1].trim(),
      }))
      return { slug: slugify(name), title: h1 ?? name, file, headings }
    }),
  )

  return { props: { topics } }
}) satisfies GetStaticProps<{ topics: DocTopic[] }>

export default function DocsPage({ topics }: InferGetStaticPropsType<typeof getStaticProps>) {
  const router = useRouter()
  const requested = typeof router.query.topic === "string" ? router.query.topic : undefined
  const active = topics.find((t) => t.slug === requested) ?? topics[0]

  const [content, setContent] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Load the selected markdown file from /public/Documentation (cached per topic).
  useEffect(() => {
    if (!active || content[active.slug] !== undefined) return
    fetch(`/${DOCS_DIR}/${encodeURIComponent(active.file)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        return res.text()
      })
      .then((text) => setContent((prev) => ({ ...prev, [active.slug]: text })))
      .catch((err: Error) => setErrors((prev) => ({ ...prev, [active.slug]: err.message })))
  }, [active, content])

  const markdown = active ? content[active.slug] : undefined
  const error = active ? errors[active.slug] : undefined

  return (
    <div className="relative flex min-h-full flex-1 flex-col">
      <div className="mx-auto grid w-full max-w-7xl flex-1 gap-8 px-4 py-8 sm:px-6 md:grid-cols-[240px_1fr]">
        {/* Topics */}
        <aside className="md:sticky md:top-24 md:h-[calc(100vh-8rem)] md:overflow-y-auto">
          <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <BookOpen className="size-3.5" />
            Documentation
          </h2>
          <nav>
            <ul className="space-y-1">
              {topics.map((topic) => {
                const isActive = topic.slug === active?.slug
                return (
                  <li key={topic.slug}>
                    <Link
                      href={{ pathname: "/docs/page", query: { topic: topic.slug } }}
                      shallow
                      scroll={false}
                      className={cn(
                        "block rounded-lg px-3 py-2 text-sm transition",
                        isActive
                          ? "bg-brand-teal/10 font-medium text-brand-teal"
                          : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                      )}
                    >
                      {topic.title}
                    </Link>
                    {isActive && topic.headings.length > 0 && (
                      <ul className="mt-1 mb-2 ml-3 space-y-0.5 border-l pl-3">
                        {topic.headings.map((h) => (
                          <li key={h.id}>
                            <a
                              href={`#${h.id}`}
                              className="block py-1 text-sm text-muted-foreground transition hover:text-foreground"
                            >
                              {h.text}
                            </a>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          </nav>
        </aside>

        {/* Content */}
        <main className="min-w-0 rounded-2xl border bg-card p-6 sm:p-10">
          {topics.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documentation yet.</p>
          ) : error ? (
            <p className="text-sm text-destructive">Couldn&apos;t load {active?.file}: {error}</p>
          ) : markdown === undefined ? (
            <div className="flex justify-center py-16">
              <LoaderCircle className="size-6 animate-spin text-brand-teal" />
            </div>
          ) : (
            <article className="max-w-3xl">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {markdown}
              </ReactMarkdown>
            </article>
          )}
        </main>
      </div>
    </div>
  )
}

function headingText(children: React.ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children)
  if (Array.isArray(children)) return children.map(headingText).join("")
  return ""
}

// Tailwind styling for rendered markdown; h2 gets an id so sidebar subtopics can jump to it.
const markdownComponents: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => (
    <h1 className="mb-6 text-3xl font-semibold tracking-tight sm:text-4xl">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2
      id={slugify(headingText(children))}
      className="mt-10 mb-4 scroll-mt-24 border-b pb-2 text-2xl font-semibold tracking-tight"
    >
      {children}
    </h2>
  ),
  h3: ({ children }) => <h3 className="mt-8 mb-3 text-lg font-semibold">{children}</h3>,
  p: ({ children }) => <p className="my-4 leading-7 text-foreground/90">{children}</p>,
  ul: ({ children }) => <ul className="my-4 ml-6 list-disc space-y-2 marker:text-brand-teal">{children}</ul>,
  ol: ({ children }) => <ol className="my-4 ml-6 list-decimal space-y-2 marker:text-brand-teal">{children}</ol>,
  li: ({ children }) => <li className="leading-7 text-foreground/90">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  a: ({ href, children }) => (
    <a href={href} className="font-medium text-brand-teal underline-offset-4 hover:underline">
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-2 border-brand-teal/50 pl-4 text-muted-foreground italic">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={cn(className, "font-mono text-sm")}>{children}</code>
    ) : (
      <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-sm">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="my-4 overflow-x-auto rounded-xl border bg-muted/50 p-4">{children}</pre>
  ),
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto">
      <table className="w-full text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b px-3 py-2 text-left font-medium">{children}</th>,
  td: ({ children }) => <td className="border-b px-3 py-2 text-muted-foreground">{children}</td>,
  hr: () => <hr className="my-8" />,
  img: ({ src, alt }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} className="my-4 rounded-xl border" />
  ),
}

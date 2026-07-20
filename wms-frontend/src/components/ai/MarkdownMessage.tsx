import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Renderiza el markdown que devuelve el asistente (negritas, listas, tablas) con el look del chat. */
export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="text-sm leading-relaxed break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-1.5">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => <ul className="my-1.5 list-disc pl-4 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1.5 list-decimal pl-4 space-y-0.5">{children}</ol>,
          li: ({ children }) => <li className="leading-snug">{children}</li>,
          code: ({ children }) => (
            <code className="rounded bg-black/10 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
          ),
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
              {children}
            </a>
          ),
          h1: ({ children }) => <p className="my-1.5 font-semibold">{children}</p>,
          h2: ({ children }) => <p className="my-1.5 font-semibold">{children}</p>,
          h3: ({ children }) => <p className="my-1.5 font-semibold">{children}</p>,
          hr: () => <hr className="my-2 border-gray-300" />,
          blockquote: ({ children }) => (
            <blockquote className="my-1.5 border-l-2 border-gray-300 pl-2 italic">{children}</blockquote>
          ),
          table: ({ children }) => (
            <div className="my-1.5 overflow-x-auto">
              <table className="border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border border-gray-300 px-1.5 py-0.5 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border border-gray-300 px-1.5 py-0.5">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

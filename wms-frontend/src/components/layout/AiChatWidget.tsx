import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Bot, X, Send, Wrench, ChevronDown } from 'lucide-react'
import { aiApi } from '@/api/endpoints'
import type { ToolCallTrace } from '@/types'
import toast from 'react-hot-toast'

interface LocalMessage {
  id: string
  role: string
  content: string
  sources: ToolCallTrace[]
}

export function AiChatWidget() {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open])

  const chatMut = useMutation({
    mutationFn: (message: string) => aiApi.chat(message, conversationId),
    onSuccess: (res) => {
      setConversationId(res.conversation_id)
      setMessages(prev => [...prev, {
        id: `assistant-${Date.now()}`, role: 'assistant', content: res.response, sources: res.sources ?? [],
      }])
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'No se pudo contactar al asistente'),
  })

  const send = () => {
    const trimmed = input.trim()
    if (!trimmed || chatMut.isPending) return
    setMessages(prev => [...prev, { id: `user-${Date.now()}`, role: 'user', content: trimmed, sources: [] }])
    setInput('')
    chatMut.mutate(trimmed)
  }

  // La página dedicada del asistente ya tiene el chat completo — evitar el duplicado
  // flotante ahí. Este check va DESPUÉS de todos los hooks (nunca antes) para no
  // violar las Rules of Hooks cambiando cuántos hooks se llaman entre renders.
  if (location.pathname.startsWith('/ai/assistant')) return null

  return (
    <>
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-96 max-w-[calc(100vw-2rem)] h-[30rem] max-h-[calc(100vh-8rem)] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 bg-primary-600 text-white flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              <span className="text-sm font-semibold">Asistente IA</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 bg-gray-50">
            {!messages.length ? (
              <p className="text-xs text-gray-400 text-center py-10">
                Pregúntame sobre stock, KPIs, alertas o pídeme ejecutar una acción.
              </p>
            ) : (
              messages.map(m => <WidgetBubble key={m.id} message={m} />)
            )}
            {chatMut.isPending && (
              <p className="text-xs text-gray-400 flex items-center gap-1.5">
                <Bot className="h-3.5 w-3.5 animate-pulse" /> Pensando…
              </p>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="px-3 py-2.5 border-t border-gray-100 flex gap-2 bg-white shrink-0">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="Escribe tu pregunta…"
              className="flex-1 h-9 rounded-lg border border-gray-300 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <button
              onClick={send}
              disabled={!input.trim() || chatMut.isPending}
              className="h-9 w-9 shrink-0 flex items-center justify-center rounded-lg bg-primary-600 text-white disabled:opacity-40 hover:bg-primary-700 transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(v => !v)}
        title="Asistente IA"
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-primary-600 hover:bg-primary-700 text-white shadow-xl flex items-center justify-center transition-transform hover:scale-105"
      >
        {open ? <X className="h-6 w-6" /> : <Bot className="h-6 w-6" />}
      </button>
    </>
  )
}

function WidgetBubble({ message }: { message: LocalMessage }) {
  const isUser = message.role === 'user'
  const [showTools, setShowTools] = useState(false)

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
        isUser ? 'bg-primary-600 text-white' : 'bg-white border border-gray-200 text-gray-800'
      }`}>
        {message.content}
        {!isUser && message.sources.length > 0 && (
          <div className="mt-1.5 pt-1.5 border-t border-gray-100">
            <button
              onClick={() => setShowTools(v => !v)}
              className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-700 transition-colors"
            >
              <Wrench className="h-3 w-3" /> {message.sources.length} herramienta(s)
              <ChevronDown className={`h-3 w-3 transition-transform ${showTools ? 'rotate-180' : ''}`} />
            </button>
            {showTools && (
              <div className="mt-1 space-y-1">
                {message.sources.map((s, i) => (
                  <p key={i} className="text-[10px] font-mono text-gray-500 break-all">
                    {s.tool}: {JSON.stringify(s.result)}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

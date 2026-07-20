import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot, Send, Plus, User as UserIcon, Wrench, ChevronDown, MessageSquare, Mic, PhoneOff, Volume2, VolumeX } from 'lucide-react'
import { aiApi } from '@/api/endpoints'
import { useVoiceConversation } from '@/hooks/useVoiceConversation'
import { useAssistantVoice } from '@/hooks/useAssistantVoice'
import { MarkdownMessage } from '@/components/ai/MarkdownMessage'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { fmt } from '@/utils/format'
import type { AIConversationMessage, ToolCallTrace } from '@/types'
import toast from 'react-hot-toast'

interface LocalMessage {
  id: string
  role: string
  content: string
  sources: ToolCallTrace[]
  pending?: boolean
}

const QUICK_QUESTIONS = [
  '¿Cuánto stock disponible tengo en total?',
  '¿Cuáles son los KPIs de inbound hoy?',
  '¿Cuáles son los KPIs de outbound hoy?',
  'Dame las alertas de reposición activas',
  '¿Hay anomalías de inventario sin resolver?',
  'Lista las órdenes de compra pendientes',
  'Lista las órdenes de venta abiertas',
  '¿Cuáles son las bodegas configuradas?',
]

export function AssistantPage() {
  const qc = useQueryClient()
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const voice = useAssistantVoice()
  const sendRef = useRef<(text: string) => void>(() => {})
  const resumeRef = useRef<() => void>(() => {})
  const conv = useVoiceConversation((text) => sendRef.current(text))

  const { data: conversations } = useQuery({
    queryKey: ['ai-conversations'],
    queryFn: () => aiApi.getConversations({ page_size: 30 }),
  })

  const { data: detail } = useQuery({
    queryKey: ['ai-conversation', conversationId],
    queryFn: () => aiApi.getConversation(conversationId!),
    enabled: !!conversationId,
  })

  useEffect(() => {
    if (detail) {
      setMessages(detail.messages.map((m: AIConversationMessage) => ({
        id: m.id, role: m.role, content: m.content, sources: m.sources ?? [],
      })))
    }
  }, [detail])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const chatMut = useMutation({
    mutationFn: (message: string) => aiApi.chat(message, conversationId),
    onSuccess: (res) => {
      setConversationId(res.conversation_id)
      const id = `assistant-${Date.now()}`
      setMessages(prev => [...prev, { id, role: 'assistant', content: res.response, sources: res.sources ?? [] }])
      qc.invalidateQueries({ queryKey: ['ai-conversations'] })
      // En modo conversación, el mic solo se reabre cuando el asistente TERMINÓ de
      // hablar (onEnded) — nunca mientras suena, para no auto-escucharse a sí mismo.
      if (voice.enabled) voice.speak(id, res.response, () => resumeRef.current())
      else resumeRef.current()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'No se pudo contactar al asistente')
      setMessages(prev => prev.filter(m => !m.pending))
      resumeRef.current()
    },
  })

  sendRef.current = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || chatMut.isPending) return
    setMessages(prev => [...prev, { id: `user-${Date.now()}`, role: 'user', content: trimmed, sources: [] }])
    chatMut.mutate(trimmed)
  }
  resumeRef.current = () => conv.resumeListening()

  const send = (override?: string) => {
    const trimmed = (override ?? input).trim()
    if (!trimmed) return
    setInput('')
    sendRef.current(trimmed)
  }

  const startNewConversation = () => {
    conv.stop()
    setConversationId(undefined)
    setMessages([])
  }

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)]">
      {/* Panel de conversaciones */}
      <Card padding={false} className="w-64 shrink-0 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <Button size="sm" className="w-full" onClick={startNewConversation}>
            <Plus className="h-4 w-4" /> Nueva conversación
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {!conversations?.items.length ? (
            <p className="text-xs text-gray-400 italic px-4 py-3">Aún no hay conversaciones.</p>
          ) : (
            conversations.items.map(c => (
              <button
                key={c.id}
                onClick={() => setConversationId(c.id)}
                className={`w-full text-left px-4 py-2.5 border-b border-gray-50 hover:bg-gray-50 transition-colors ${
                  conversationId === c.id ? 'bg-primary-50 border-l-2 border-l-primary-600' : ''
                }`}
              >
                <p className="text-sm font-medium text-gray-800 truncate flex items-center gap-1.5">
                  <MessageSquare className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                  {c.title || 'Nueva conversación'}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">{c.message_count} mensajes · {fmt.relative(c.updated_at)}</p>
              </button>
            ))
          )}
        </div>
      </Card>

      {/* Panel de chat */}
      <Card padding={false} className="flex-1 flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary-600" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-gray-900">Asistente IA del WMS</p>
            <p className="text-xs text-gray-400">Consulta inventario, inbound, outbound, maestros, bodegas y más — y ejecuta acciones reales (labor, alertas, anomalías)</p>
          </div>
          <button
            onClick={() => voice.setEnabled(!voice.enabled)}
            title={voice.enabled ? 'Respuestas por voz activadas — clic para desactivar' : 'Respuestas por voz desactivadas — clic para activar'}
            className={`h-8 w-8 shrink-0 flex items-center justify-center rounded-lg transition-colors ${
              voice.enabled ? 'text-primary-600 hover:bg-primary-50' : 'text-gray-300 hover:bg-gray-100'
            }`}
          >
            {voice.enabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {!messages.length && (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 gap-4 px-4">
              <Bot className="h-10 w-10 text-gray-300" />
              <p className="text-sm">Pregúntame sobre stock, KPIs, alertas o pídeme ejecutar una acción.</p>
              <div className="flex flex-wrap justify-center gap-2 max-w-xl">
                {QUICK_QUESTIONS.map(q => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    disabled={chatMut.isPending}
                    className="text-xs px-3 py-1.5 rounded-full border border-gray-200 bg-white text-gray-600 hover:border-primary-300 hover:text-primary-700 hover:bg-primary-50 transition-colors disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map(m => (
            <MessageBubble
              key={m.id}
              message={m}
              isSpeaking={voice.speakingId === m.id}
              onSpeak={() => voice.speak(m.id, m.content)}
            />
          ))}
          {chatMut.isPending && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Bot className="h-4 w-4 animate-pulse" /> Pensando…
            </div>
          )}
          {conv.state === 'transcribing' && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Mic className="h-4 w-4 animate-pulse" /> Transcribiendo audio…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {conv.active && (
          <div className="px-4 pt-2 flex items-center justify-center gap-1.5 text-xs font-medium text-primary-600">
            <span className={`h-1.5 w-1.5 rounded-full bg-primary-600 ${conv.state === 'listening' ? 'animate-pulse' : 'animate-ping'}`} />
            {conv.state === 'listening' ? 'Escuchando… habla cuando quieras'
              : conv.state === 'transcribing' ? 'Entendiendo lo que dijiste…'
              : chatMut.isPending ? 'El asistente está pensando…'
              : voice.speakingId ? 'El asistente está hablando…'
              : 'Conversación activa — di tu siguiente pregunta'}
          </div>
        )}
        <div className="px-4 py-3 border-t border-gray-100 flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder={conv.state === 'listening' ? 'Escuchando…' : 'Escribe o inicia la conversación por voz…'}
            className="flex-1 h-10 rounded-lg border border-gray-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <Button
            size="sm"
            variant={conv.active ? 'danger' : 'secondary'}
            onClick={conv.toggle}
            title={conv.active ? 'Terminar conversación por voz' : 'Iniciar conversación por voz (manos libres)'}
            className={`h-10 px-3 ${conv.state === 'listening' ? 'animate-pulse' : ''}`}
          >
            {conv.active ? <PhoneOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </Button>
          <Button size="sm" disabled={!input.trim() || chatMut.isPending} onClick={() => send()} className="h-10 px-4">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </Card>
    </div>
  )
}

function MessageBubble({ message, isSpeaking, onSpeak }: {
  message: LocalMessage
  isSpeaking?: boolean
  onSpeak?: () => void
}) {
  const isUser = message.role === 'user'
  const [showTools, setShowTools] = useState(false)

  return (
    <div className={`flex gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-primary-100 flex items-center justify-center shrink-0">
          <Bot className="h-4 w-4 text-primary-600" />
        </div>
      )}
      <div className={`max-w-[75%] rounded-xl px-4 py-2.5 ${
        isUser ? 'bg-primary-600 text-white text-sm whitespace-pre-wrap' : 'bg-gray-100 text-gray-800'
      }`}>
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            {isUser ? message.content : <MarkdownMessage content={message.content} />}
          </div>
          {!isUser && onSpeak && (
            <button
              onClick={onSpeak}
              title="Escuchar respuesta"
              className={`shrink-0 mt-0.5 h-5 w-5 flex items-center justify-center rounded transition-colors ${
                isSpeaking ? 'text-primary-600 animate-pulse' : 'text-gray-400 hover:text-primary-600'
              }`}
            >
              <Volume2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {!isUser && message.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-200">
            <button
              onClick={() => setShowTools(v => !v)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              <Wrench className="h-3 w-3" /> {message.sources.length} herramienta(s) usada(s)
              <ChevronDown className={`h-3 w-3 transition-transform ${showTools ? 'rotate-180' : ''}`} />
            </button>
            {showTools && (
              <div className="mt-2 space-y-1.5">
                {message.sources.map((s, i) => (
                  <div key={i} className="rounded-lg bg-white border border-gray-200 p-2 text-xs">
                    <p className="font-mono font-semibold text-primary-700">{s.tool}</p>
                    {Object.keys(s.args ?? {}).length > 0 && (
                      <p className="text-gray-500 mt-0.5">args: <span className="font-mono">{JSON.stringify(s.args)}</span></p>
                    )}
                    <p className="text-gray-500 mt-0.5">resultado: <span className="font-mono">{JSON.stringify(s.result)}</span></p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center shrink-0">
          <UserIcon className="h-4 w-4 text-gray-500" />
        </div>
      )}
    </div>
  )
}

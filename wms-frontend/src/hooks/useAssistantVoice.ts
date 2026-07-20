import { useCallback, useEffect, useRef, useState } from 'react'
import { aiApi } from '@/api/endpoints'
import toast from 'react-hot-toast'

const STORAGE_KEY = 'wms:ai_voice_enabled'

function readEnabled(): boolean {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw === null ? true : raw === 'true'
}

/**
 * Reproduce las respuestas del asistente como voz (TTS vía backend).
 * Usa un token de secuencia: cada speak() invalida cualquier solicitud/reproducción
 * anterior en curso, así nunca suenan dos audios superpuestos (eco) aunque se
 * dispare la reproducción automática y luego el usuario pida repetir manualmente.
 */
export function useAssistantVoice() {
  const [enabled, setEnabledState] = useState(readEnabled)
  const [speakingId, setSpeakingId] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlRef = useRef<string | null>(null)
  const seqRef = useRef(0)

  const stop = useCallback(() => {
    seqRef.current += 1 // invalida cualquier fetch/reproducción en curso
    audioRef.current?.pause()
    audioRef.current = null
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
    setSpeakingId(null)
  }, [])

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value)
    localStorage.setItem(STORAGE_KEY, String(value))
    if (!value) stop()
  }, [stop])

  /**
   * `onEnded` se dispara exactamente una vez cuando este audio termina (o falla) —
   * es el gancho que usa el modo de conversación por voz para reabrir el micrófono
   * automáticamente solo después de que el asistente terminó de hablar.
   */
  const speak = useCallback(async (id: string, text: string, onEnded?: () => void) => {
    stop()
    const mySeq = seqRef.current

    let blob: Blob
    try {
      blob = await aiApi.speak(text)
    } catch {
      toast.error('No se pudo generar el audio de la respuesta.')
      if (seqRef.current === mySeq) onEnded?.()
      return
    }
    if (seqRef.current !== mySeq) return // reemplazado por otra solicitud mientras esperábamos la red

    const url = URL.createObjectURL(blob)
    urlRef.current = url
    const audio = new Audio(url)
    audioRef.current = audio
    audio.onended = () => {
      if (seqRef.current === mySeq) {
        setSpeakingId(null)
        onEnded?.()
      }
      URL.revokeObjectURL(url)
      if (urlRef.current === url) urlRef.current = null
    }
    audio.onerror = () => {
      if (seqRef.current === mySeq) { setSpeakingId(null); onEnded?.() }
    }
    setSpeakingId(id)
    try {
      await audio.play()
    } catch {
      // El navegador bloqueó la reproducción automática (política de autoplay) —
      // avisamos en vez de fallar en silencio, porque si no el usuario nunca
      // entiende por qué "no dictó automático" y termina reintentando a mano.
      if (seqRef.current === mySeq) {
        setSpeakingId(null)
        toast.error('El navegador bloqueó la voz automática — toca 🔊 en el mensaje para escucharlo.')
        onEnded?.()
      }
    }
  }, [stop])

  // Al desmontar (cambiar de página, cerrar el widget) corta cualquier audio en curso.
  useEffect(() => () => { audioRef.current?.pause() }, [])

  return { enabled, setEnabled, speakingId, speak, stop }
}

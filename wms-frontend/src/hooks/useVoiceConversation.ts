import { useCallback, useEffect, useRef, useState } from 'react'
import { aiApi } from '@/api/endpoints'
import toast from 'react-hot-toast'

export type ConversationState = 'idle' | 'listening' | 'transcribing'

const SILENCE_MS = 1200        // silencio continuo para asumir que terminó de hablar
const MIN_SPEECH_MS = 300       // ignora ruidos brevísimos (no cuenta como "habló")
const MAX_RECORDING_MS = 20000  // límite de seguridad por si el VAD no detecta silencio
const SPEECH_RMS_THRESHOLD = 0.02

/**
 * Modo de conversación por voz manos-libres: graba, detecta automáticamente
 * cuándo el usuario dejó de hablar (VAD por volumen, sin botones), transcribe
 * y entrega el texto via `onUserText`. El llamador decide cuándo reabrir el
 * micrófono (típicamente cuando el asistente terminó de leer su respuesta)
 * llamando a `resumeListening()`.
 */
export function useVoiceConversation(onUserText: (text: string) => void) {
  const [active, setActive] = useState(false)
  const [state, setState] = useState<ConversationState>('idle')

  const activeRef = useRef(false)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef<number | null>(null)
  const silenceStartRef = useRef<number | null>(null)
  const speechStartRef = useRef<number | null>(null)
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const startRecordingRef = useRef<() => void>(() => {})
  const onUserTextRef = useRef(onUserText)
  onUserTextRef.current = onUserText

  const cleanupAnalysis = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    analyserRef.current = null
    if (audioCtxRef.current) audioCtxRef.current.close().catch(() => {})
    audioCtxRef.current = null
    silenceStartRef.current = null
    speechStartRef.current = null
    if (maxTimerRef.current) { clearTimeout(maxTimerRef.current); maxTimerRef.current = null }
  }, [])

  const stopRecorder = useCallback(() => {
    cleanupAnalysis()
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
  }, [cleanupAnalysis])

  const stopAll = useCallback(() => {
    activeRef.current = false
    setActive(false)
    stopRecorder()
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    setState('idle')
  }, [stopRecorder])

  const watchSilence = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser) return
    const data = new Uint8Array(analyser.fftSize)

    const tick = () => {
      if (!analyserRef.current) return
      analyser.getByteTimeDomainData(data)
      let sumSquares = 0
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128
        sumSquares += v * v
      }
      const rms = Math.sqrt(sumSquares / data.length)
      const now = performance.now()

      if (rms > SPEECH_RMS_THRESHOLD) {
        if (speechStartRef.current === null) speechStartRef.current = now
        silenceStartRef.current = null
      } else if (speechStartRef.current !== null && now - speechStartRef.current > MIN_SPEECH_MS) {
        if (silenceStartRef.current === null) silenceStartRef.current = now
        else if (now - silenceStartRef.current > SILENCE_MS) {
          stopRecorder()
          return
        }
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [stopRecorder])

  const startRecording = useCallback(async () => {
    if (!activeRef.current) return
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      toast.error('Tu navegador no soporta grabación de audio.')
      stopAll()
      return
    }
    try {
      const stream = streamRef.current ?? await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      if (!activeRef.current) { stream.getTracks().forEach(t => t.stop()); return }

      const AudioCtxCls = window.AudioContext ?? (window as any).webkitAudioContext
      const audioCtx: AudioContext = new AudioCtxCls()
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 1024
      source.connect(analyser)
      audioCtxRef.current = audioCtx
      analyserRef.current = analyser

      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }

      recorder.onstop = async () => {
        cleanupAnalysis()
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        chunksRef.current = []
        if (!activeRef.current) { setState('idle'); return }

        if (blob.size === 0) {
          startRecordingRef.current() // nada capturado — sigue escuchando
          return
        }
        setState('transcribing')
        try {
          const { text } = await aiApi.transcribe(blob)
          if (!activeRef.current) return
          if (text?.trim()) {
            setState('idle') // el llamador reabre el mic cuando el asistente termine de responder/hablar
            onUserTextRef.current(text.trim())
          } else {
            startRecordingRef.current() // no se entendió nada — reintenta sin pedirle nada al usuario
          }
        } catch {
          toast.error('No se pudo transcribir el audio.')
          if (activeRef.current) setState('idle')
        }
      }

      recorderRef.current = recorder
      recorder.start()
      setState('listening')
      maxTimerRef.current = setTimeout(() => stopRecorder(), MAX_RECORDING_MS)
      watchSilence()
    } catch {
      toast.error('No se pudo acceder al micrófono. Verifica los permisos del navegador.')
      stopAll()
    }
  }, [cleanupAnalysis, stopAll, stopRecorder, watchSilence])

  startRecordingRef.current = startRecording

  const start = useCallback(() => {
    activeRef.current = true
    setActive(true)
    startRecording()
  }, [startRecording])

  const resumeListening = useCallback(() => {
    if (activeRef.current) startRecording()
  }, [startRecording])

  const toggle = useCallback(() => {
    if (activeRef.current) stopAll()
    else start()
  }, [start, stopAll])

  useEffect(() => () => stopAll(), [stopAll])

  return { active, state, toggle, resumeListening, stop: stopAll }
}

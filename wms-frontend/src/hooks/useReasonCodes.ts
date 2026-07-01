import { useState, useCallback } from 'react'

const STORAGE_KEY = 'wms:custom_reason_codes'

export interface ReasonCode {
  code: string
  label: string
  isSystem: boolean
}

// Códigos de sistema — no se pueden borrar
const SYSTEM_CODES: ReasonCode[] = [
  { code: 'DAMAGE',      label: 'Mercancía Dañada',   isSystem: true },
  { code: 'EXPIRED',     label: 'Vencimiento',         isSystem: true },
  { code: 'COUNT_ERROR', label: 'Error de Conteo',     isSystem: true },
  { code: 'THEFT',       label: 'Robo / Pérdida',      isSystem: true },
  { code: 'FOUND',       label: 'Hallazgo / Sobrante', isSystem: true },
  { code: 'OTHER',       label: 'Otro',                isSystem: true },
]

function readCustom(): ReasonCode[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeCustom(codes: ReasonCode[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(codes))
}

export function useReasonCodes() {
  const [custom, setCustom] = useState<ReasonCode[]>(readCustom)

  const all: ReasonCode[] = [...SYSTEM_CODES, ...custom]

  const addCode = useCallback((code: string, label: string) => {
    const normalized = code.trim().toUpperCase().replace(/\s+/g, '_')
    if (!normalized || all.some(c => c.code === normalized)) return false
    const entry: ReasonCode = { code: normalized, label: label.trim() || normalized, isSystem: false }
    setCustom(prev => {
      const next = [...prev, entry]
      writeCustom(next)
      return next
    })
    return true
  }, [all])

  const removeCode = useCallback((code: string) => {
    setCustom(prev => {
      const next = prev.filter(c => c.code !== code)
      writeCustom(next)
      return next
    })
  }, [])

  // Lista plana de strings para el <select> del formulario
  const codeList = all.map(c => c.code)

  return { all, codeList, addCode, removeCode }
}

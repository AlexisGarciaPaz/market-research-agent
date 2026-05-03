"use client"

import { useEffect, useRef, useState } from "react"
import { X, ScanLine, Loader2, AlertCircle } from "lucide-react"

interface Props {
  onResult: (codigo: string) => void
  onClose:  () => void
}

export function BarcodeScanner({ onResult, onClose }: Props) {
  const videoRef  = useRef<HTMLVideoElement>(null)
  const stopRef   = useRef<(() => void) | null>(null)
  const [error,   setError]   = useState("")
  const [decoded, setDecoded] = useState("")

  useEffect(() => {
    let cancelled = false

    async function iniciar() {
      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser")
        const reader = new BrowserMultiFormatReader()

        if (!videoRef.current || cancelled) return

        const controls = await reader.decodeFromVideoDevice(
          undefined,
          videoRef.current,
          (result, err) => {
            if (result && !cancelled) {
              cancelled = true
              controls.stop()
              const code = result.getText()
              setDecoded(code)
              setTimeout(() => onResult(code), 300)
            }
          }
        )

        stopRef.current = () => controls.stop()
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e)
          if (msg.toLowerCase().includes("permission") || msg.toLowerCase().includes("denied")) {
            setError("Permiso de cámara denegado. Actívalo en la configuración del navegador.")
          } else {
            setError("No se pudo acceder a la cámara.")
          }
        }
      }
    }

    iniciar()

    return () => {
      cancelled = true
      stopRef.current?.()
    }
  }, [onResult])

  return (
    <div className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-zinc-900 rounded-2xl overflow-hidden shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <ScanLine className="w-4 h-4 text-zinc-400" />
            <span className="text-sm font-medium text-zinc-200">Escanear código de barras</span>
          </div>
          <button onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 transition-colors p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Visor */}
        <div className="relative bg-black" style={{ aspectRatio: "4/3" }}>
          <video
            ref={videoRef}
            className="w-full h-full object-cover"
            muted
            playsInline
            autoPlay
          />

          {/* Marco de encuadre */}
          {!error && !decoded && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="relative w-64 h-28">
                {/* Esquinas */}
                <span className="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-white rounded-tl" />
                <span className="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-white rounded-tr" />
                <span className="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-white rounded-bl" />
                <span className="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-white rounded-br" />
                {/* Línea de escaneo animada */}
                <div className="absolute left-1 right-1 h-px bg-red-400/80 animate-scan" />
              </div>
            </div>
          )}

          {/* Feedback de código detectado */}
          {decoded && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60">
              <div className="flex items-center gap-2 bg-emerald-900/80 border border-emerald-700 px-4 py-2.5 rounded-xl">
                <Loader2 className="w-4 h-4 text-emerald-300 animate-spin" />
                <span className="text-sm text-emerald-200 font-mono">{decoded}</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3">
          {error ? (
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-sm text-red-400">{error}</p>
            </div>
          ) : (
            <p className="text-xs text-zinc-600 text-center">
              Apunta la cámara al código EAN-13 o UPC-A del producto
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

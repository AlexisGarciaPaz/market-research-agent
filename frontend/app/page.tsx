"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Search, Package, DollarSign, Hash, ChevronRight, Loader2, Link, TrendingUp, ShoppingCart } from "lucide-react"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

function extraerAsin(url: string): string {
  const m = url.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/)
  return m ? m[1] : ""
}

export default function HomePage() {
  const router = useRouter()
  const [producto,     setProducto]     = useState("")
  const [precio,       setPrecio]       = useState("")
  const [unidades,     setUnidades]     = useState("1")
  const [urlAmazon,    setUrlAmazon]    = useState("")
  const [precioAmazon, setPrecioAmazon] = useState("")
  const [ventasMes,    setVentasMes]    = useState("")
  const [loading,      setLoading]      = useState(false)
  const [error,        setError]        = useState("")

  const asin = extraerAsin(urlAmazon)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")

    const precioNum = parseFloat(precio)
    if (!producto.trim()) return setError("Escribe el nombre del producto")
    if (!precioNum || precioNum <= 0) return setError("Escribe un precio válido")

    setLoading(true)
    try {
      if (!API_URL) throw new Error("API no configurada — contacta al administrador")

      const res = await fetch(`${API_URL}/validar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          producto:      producto.trim(),
          precio_compra: precioNum,
          unidades:      parseInt(unidades) || 1,
          url_amazon:    urlAmazon.trim(),
          precio_amazon: parseFloat(precioAmazon) || 0,
          ventas_mes:    parseInt(ventasMes) || 0,
        }),
      })

      if (!res.ok) {
        let msg = `Error ${res.status}`
        try {
          const data = await res.json()
          msg = data.detail || msg
        } catch { /* respuesta no JSON */ }
        throw new Error(msg)
      }

      const { job_id } = await res.json()
      const params = new URLSearchParams({
        producto, precio, unidades,
        ...(urlAmazon    && { url:         urlAmazon }),
        ...(precioAmazon && { precioAmazon }),
        ...(ventasMes    && { ventasMes }),
      })
      router.push(`/analisis/${job_id}?${params}`)
    } catch (err: any) {
      setError(err.message || "No se pudo conectar al servidor")
      setLoading(false)
    }
  }

  return (
    <main className="flex flex-col flex-1 px-5 pt-16 pb-8">
      {/* Header */}
      <div className="mb-10">
        <div className="w-10 h-10 bg-zinc-800 rounded-xl flex items-center justify-center mb-4">
          <Search className="w-5 h-5 text-zinc-300" />
        </div>
        <h1 className="text-2xl font-bold text-zinc-50 leading-tight">
          Validador de productos
        </h1>
        <p className="text-zinc-400 text-sm mt-2 leading-relaxed">
          Ingresa cualquier producto que encuentres y te digo si conviene venderlo en Amazon México.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* Product name */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Producto
          </label>
          <div className="relative">
            <Package className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="text"
              value={producto}
              onChange={(e) => setProducto(e.target.value)}
              placeholder="NOW Foods Vitamina C-1000 100 Cápsulas"
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-4 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
              disabled={loading}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
            />
          </div>
        </div>

        {/* Purchase price */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Precio de compra (MX$)
          </label>
          <div className="relative">
            <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="number"
              value={precio}
              onChange={(e) => setPrecio(e.target.value)}
              placeholder="140"
              inputMode="decimal"
              min="1"
              step="0.01"
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-4 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
              disabled={loading}
            />
          </div>
        </div>

        {/* Units */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Unidades a comprar
          </label>
          <div className="relative">
            <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="number"
              value={unidades}
              onChange={(e) => setUnidades(e.target.value)}
              placeholder="12"
              inputMode="numeric"
              min="1"
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-4 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
              disabled={loading}
            />
          </div>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3 my-1">
          <div className="flex-1 h-px bg-zinc-800" />
          <span className="text-xs text-zinc-600">Datos de Amazon (opcional)</span>
          <div className="flex-1 h-px bg-zinc-800" />
        </div>

        {/* Amazon URL */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            URL del producto en Amazon
          </label>
          <div className="relative">
            <Link className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="url"
              value={urlAmazon}
              onChange={(e) => setUrlAmazon(e.target.value)}
              placeholder="https://www.amazon.com.mx/dp/B0C29KV9TH"
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-4 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
              disabled={loading}
              autoComplete="off"
            />
          </div>
          {asin && (
            <p className="text-xs text-emerald-500 pl-1">
              ASIN detectado: <span className="font-mono font-semibold">{asin}</span>
            </p>
          )}
        </div>

        {/* Amazon price + monthly sales side by side */}
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
              Precio en Amazon
            </label>
            <div className="relative">
              <ShoppingCart className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                type="number"
                value={precioAmazon}
                onChange={(e) => setPrecioAmazon(e.target.value)}
                placeholder="299"
                inputMode="decimal"
                min="0"
                step="0.01"
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-3 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
                disabled={loading}
              />
            </div>
            <p className="text-xs text-zinc-600">Precio actual MX$</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
              Ventas/mes
            </label>
            <div className="relative">
              <TrendingUp className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                type="number"
                value={ventasMes}
                onChange={(e) => setVentasMes(e.target.value)}
                placeholder="1500"
                inputMode="numeric"
                min="0"
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-10 pr-3 py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
                disabled={loading}
              />
            </div>
            <p className="text-xs text-zinc-600">Comprados este mes</p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-950/50 border border-red-900/50 rounded-xl px-4 py-3 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full bg-zinc-50 hover:bg-zinc-200 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-950 font-semibold rounded-xl py-4 flex items-center justify-center gap-2 transition-colors text-sm"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Iniciando análisis...
            </>
          ) : (
            <>
              Analizar producto
              <ChevronRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      <p className="mt-auto pt-8 text-center text-xs text-zinc-700">
        El análisis tarda ~5 min y usa IA para evaluar el mercado
      </p>
    </main>
  )
}

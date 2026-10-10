import { useEffect, useRef, useState } from 'react'

/** Call `fn` now and then every `ms` milliseconds, one at a time, until unmounted. */
export function usePoll(fn: () => Promise<void>, ms: number, deps: unknown[] = []) {
  const latest = useRef(fn)
  useEffect(() => { latest.current = fn })
  useEffect(() => {
    let alive = true
    let timer = 0
    const tick = async () => {
      try { await latest.current() } catch { /* the caller reports connection errors */ }
      if (alive) timer = window.setTimeout(tick, ms)
    }
    tick()
    return () => { alive = false; window.clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps])
}

export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined)
  useEffect(() => { ref.current = value })
  return ref.current
}

const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Roll a number toward `target`, like a till display counting. */
export function useRollingNumber(target: number, ms = 900): number {
  const [shown, setShown] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    if (reduced() || from.current === target) { from.current = target; setShown(target); return }
    const start = performance.now()
    const begin = from.current
    let raf = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 3)
      const v = begin + (target - begin) * eased
      from.current = v
      setShown(v)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return shown
}

export function useStoredState(key: string, initial: string): [string, (v: string) => void] {
  const [value, setValue] = useState(() => localStorage.getItem(key) ?? initial)
  const set = (v: string) => { setValue(v); localStorage.setItem(key, v) }
  return [value, set]
}

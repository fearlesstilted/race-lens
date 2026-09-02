import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { encodePocketAppLink, encodePocketLink, type PocketTarget } from '../../api/pocket'

export function CompanionLink({ target }: { target: PocketTarget | null }) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const [handoff, setHandoff] = useState<PocketTarget | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const dialog = useRef<HTMLElement>(null)
  const appLink = handoff ? encodePocketAppLink(handoff) : ''
  const browserLink = handoff ? encodePocketLink(handoff) : ''
  useEffect(() => {
    if (target == null && open) { setOpen(false); setHandoff(null); setCopied(null) }
  }, [open, target])
  useEffect(() => {
    if (!open) { setCopied(null); return }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
      if (event.key !== 'Tab' || !dialog.current) return
      const controls = Array.from(dialog.current.querySelectorAll<HTMLElement>('button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'))
      if (!controls.length) return
      const first = controls[0]; const last = controls.at(-1)!
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    dialog.current?.querySelector<HTMLElement>('button')?.focus()
    return () => { window.removeEventListener('keydown', onKey); trigger.current?.focus() }
  }, [open])
  const copy = async () => {
    try { await navigator.clipboard.writeText(browserLink); setCopied('LINK COPIED') }
    catch { setCopied('COPY FAILED') }
  }
  if (!target) return null
  return (
    <div className="companion-link">
      <button ref={trigger} type="button" className="companion-trigger" onClick={() => { setHandoff(target); setCopied(null); setOpen(true) }} aria-haspopup="dialog" aria-expanded={open}>
        <span className="companion-dot is-linked" aria-hidden="true" />
        <span>OPEN IN POCKET</span>
      </button>
      {open && <div className="companion-overlay">
        <button type="button" className="companion-backdrop" onClick={() => setOpen(false)} aria-label="Close Pocket handoff" />
        <section ref={dialog} className="companion-panel" role="dialog" aria-modal="true" aria-labelledby="pocket-title">
          <header className="companion-header">
            <div><small>RACE LENS POCKET</small><h2 id="pocket-title">Open independently</h2></div>
            <button type="button" className="settings-close" onClick={() => { setOpen(false); setHandoff(null) }} aria-label="Close">×</button>
          </header>
          <div className="companion-share">
            <div className="companion-qr"><QRCodeSVG value={appLink} size={184} level="M" title="Race Lens Pocket app handoff QR code" /></div>
            <p>Scan with installed Pocket to hand off this session and focus. Pocket fetches timing directly; actions there do not change this dashboard.</p>
            <button type="button" className="b companion-primary" onClick={() => void copy()}>COPY BROWSER LINK</button>
            {copied && <small role="status">{copied}</small>}
          </div>
        </section>
      </div>}
    </div>
  )
}

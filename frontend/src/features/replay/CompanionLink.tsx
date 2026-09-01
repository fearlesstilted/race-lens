import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import type { CompanionLinkModel } from '../../api/companion'

type Props = {
  model: CompanionLinkModel
  canCreate: boolean
}

const STATUS_LABEL = {
  disconnected: 'DISCONNECTED',
  linked: 'LINKED',
  reconnecting: 'RECONNECTING',
  expired: 'EXPIRED',
} as const

export function CompanionLink({ model, canCreate }: Props) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const panel = useRef<HTMLElement | null>(null)
  const trigger = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    const triggerElement = trigger.current
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
      if (event.key !== 'Tab' || !panel.current) return
      const controls = Array.from(panel.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
      ))
      if (!controls.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => {
      window.removeEventListener('keydown', handleKey)
      triggerElement?.focus()
    }
  }, [open])

  const copy = async () => {
    if (!model.shareUrl) return
    try {
      await navigator.clipboard.writeText(model.shareUrl)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="companion-link">
      <button
        ref={trigger}
        type="button"
        className="companion-trigger"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Link devices"
      >
        <span className={`companion-dot is-${model.status}`} aria-hidden="true" />
        <span>LINK DEVICES</span>
      </button>

      {open && (
        <div className="companion-overlay">
          <button
            type="button"
            className="companion-backdrop"
            onClick={() => setOpen(false)}
            aria-label="Close Companion Link"
          />
          <section
            ref={panel}
            className="companion-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="companion-title"
          >
            <header className="companion-header">
              <div>
                <small>RACE LENS POCKET</small>
                <h2 id="companion-title">Companion Link</h2>
              </div>
              <button autoFocus type="button" className="settings-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
            </header>

            <div className={`companion-status is-${model.status}`} role="status" aria-live="polite">
              <span className={`companion-dot is-${model.status}`} aria-hidden="true" />
              <b>{STATUS_LABEL[model.status]}</b>
              <small>
                {model.status === 'linked' && 'VIEW IS SYNCHRONIZED'}
                {model.status === 'reconnecting' && 'RETRYING AUTOMATICALLY'}
                {model.status === 'expired' && 'CREATE A NEW LINK TO CONTINUE'}
                {model.status === 'disconnected' && 'NO DEVICES LINKED'}
              </small>
            </div>

            {model.shareUrl && model.status !== 'expired' ? (
              <div className="companion-share">
                <div className="companion-qr">
                  <QRCodeSVG value={model.shareUrl} size={184} level="M" title="Companion Link QR code" />
                </div>
                <p>Scan with the Race Lens mobile app or open the link on another device.</p>
                <button type="button" className="b companion-primary" onClick={() => void copy()}>
                  {copied ? 'LINK COPIED' : 'COPY LINK'}
                </button>
                <button type="button" className="b companion-leave" onClick={model.leave}>LEAVE</button>
              </div>
            ) : (
              <div className="companion-empty">
                <p>Link this dashboard with another Race Lens device. Each device keeps fetching race data directly.</p>
                {model.createError && (
                  <div className="companion-error" role="alert">{model.createError}</div>
                )}
                <button
                  type="button"
                  className="b companion-primary"
                  disabled={!canCreate || model.busy}
                  onClick={() => void model.create()}
                >
                  {model.busy ? 'CREATING…' : model.status === 'expired' ? 'CREATE NEW LINK' : 'CREATE LINK'}
                </button>
                {!canCreate && <small>OPEN A REPLAY OR LIVE SESSION FIRST</small>}
                {model.status === 'expired' && (
                  <button type="button" className="b companion-leave" onClick={model.leave}>LEAVE</button>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

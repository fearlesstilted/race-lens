import { restartCountdown } from '../../lib/liveStatus'

type Props = {
  status: string
  lap?: number | null
  atMs?: number
  neutralizationStartMs?: number | null
  greenFlag?: boolean
  greenFlagText?: string
  restartAnnouncement?: string | null
  restartAtMs?: number | null
}

function formatNeutralTimer(atMs: number, startMs: number): string {
  const elapsed = Math.max(0, atMs - startMs)
  const totalSec = Math.floor(elapsed / 1000)
  const mm = Math.floor(totalSec / 60).toString().padStart(2, '0')
  const ss = (totalSec % 60).toString().padStart(2, '0')
  return `${mm}:${ss}`
}

export function StatusStrip({
  status,
  lap = null,
  atMs = 0,
  neutralizationStartMs = null,
  greenFlag = false,
  greenFlagText = '',
  restartAnnouncement = null,
  restartAtMs = null,
}: Props) {
  const lapStr = lap != null ? `LAP ${lap}` : ''
  const timerStr =
    neutralizationStartMs != null
      ? formatNeutralTimer(atMs, neutralizationStartMs)
      : '00:00'
  const restartTimer = restartCountdown(atMs, restartAtMs)

  if (status === 'formation') {
    return (
      <div className="hazard hazard-formation">
        <span>FORMATION LAP</span>
      </div>
    )
  }

  // Pre-start banners (formation lap / on the grid) show regardless of session
  // status — there are no events before lights-out.
  if (greenFlag && (greenFlagText === 'FORMATION LAP' || greenFlagText === 'ON THE GRID')) {
    return (
      <div className="hazard hazard-formation">
        <span>{greenFlagText}</span>
      </div>
    )
  }

  if (greenFlag && status === 'started') {
    return (
      <div className="hazard hazard-green">
        <span>{greenFlagText}</span>
      </div>
    )
  }

  if (status === 'started') return null

  if (status === 'red_flag') {
    return (
      <div className="hazard hazard-red">
        <span>
          RED FLAG · SESSION STOPPED · {timerStr}
          {restartAnnouncement ? ` · ${restartAnnouncement}` : ''}
          {restartTimer ? ` · RESUME IN ${restartTimer}` : ''}
        </span>
      </div>
    )
  }

  if (status === 'safety_car') {
    return (
      <div className="hazard hazard-amber">
        <span>SAFETY CAR{lapStr ? ` · ${lapStr}` : ''} · {timerStr}</span>
      </div>
    )
  }

  if (status === 'vsc') {
    return (
      <div className="hazard hazard-amber">
        <span>VIRTUAL SAFETY CAR{lapStr ? ` · ${lapStr}` : ''} · {timerStr}</span>
      </div>
    )
  }

  if (status === 'finished') {
    return (
      <div className="hazard hazard-chequered">
        <span>CHEQUERED FLAG</span>
      </div>
    )
  }

  return null
}

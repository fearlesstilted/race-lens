import React from 'react'

type Props = {
  status: string
  greenFlag?: boolean
  greenFlagText?: string
}

export function StatusStrip({ status, greenFlag = false, greenFlagText = '' }: Props) {
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
        <span>RED FLAG</span>
      </div>
    )
  }

  if (status === 'safety_car') {
    return (
      <div className="hazard hazard-amber">
        <span>SAFETY CAR</span>
      </div>
    )
  }

  if (status === 'vsc') {
    return (
      <div className="hazard hazard-amber">
        <span>VIRTUAL SAFETY CAR</span>
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

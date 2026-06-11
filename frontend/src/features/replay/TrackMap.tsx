import React from 'react'

export function TrackMap() {
  return (
    <div className="map">
      <svg width="460" height="270" viewBox="0 0 460 270" fill="none">
        <path
          d="M70 215 C45 170 55 125 100 103 C145 81 165 45 220 40 C275 35 305 57 340 79 C383 106 415 122 404 166 C393 204 348 198 315 214 C271 236 238 250 183 244 C128 238 92 256 70 215 Z"
          stroke="#26262e"
          strokeWidth="16"
          strokeLinejoin="round"
        />
        <path
          d="M70 215 C45 170 55 125 100 103 C145 81 165 45 220 40"
          stroke="#3d3d49"
          strokeWidth="16"
          strokeLinejoin="round"
        />
      </svg>
      <span className="note">SCHEMATIC — NEXT MILESTONE</span>
    </div>
  )
}

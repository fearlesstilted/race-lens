import type { WeatherState } from '../api/types'

export function formatWeather(weather?: WeatherState | null): string | null {
  if (!weather) return null
  const parts: string[] = []
  if (weather.rainfall != null) parts.push(weather.rainfall ? 'RAIN' : 'DRY')
  if (weather.track_temp_c != null) parts.push(`TRACK ${weather.track_temp_c.toFixed(1)}°`)
  if (weather.air_temp_c != null) parts.push(`AIR ${weather.air_temp_c.toFixed(1)}°`)
  return parts.length ? parts.join(' · ') : null
}

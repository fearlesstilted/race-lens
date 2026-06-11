export const TEAM_COLORS: Record<string, string> = {
  LEC: '#e10600',
  SAI: '#e10600',
  PIA: '#ff8700',
  NOR: '#ff8700',
  RUS: '#00d2be',
  HAM: '#00d2be',
  VER: '#0600ef',
  PER: '#0600ef',
  TSU: '#2b4562',
  RIC: '#2b4562',
  ALO: '#006f62',
  STR: '#006f62',
  GAS: '#0090ff',
  OCO: '#0090ff',
  ALB: '#005aff',
  SAR: '#005aff',
  BOT: '#900000',
  ZHO: '#900000',
  MAG: '#ffffff',
  HUL: '#ffffff',
}

export const teamColor = (driverCode: string): string =>
  TEAM_COLORS[driverCode.toUpperCase()] ?? '#555555'

const apiBase = (import.meta.env?.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export function withApiBase(path: string, base = apiBase): string {
  if (!path.startsWith('/api/')) throw new Error(`API path must start with /api/: ${path}`)
  return `${base.replace(/\/$/, '')}${path}`
}

export const apiUrl = (path: string) => withApiBase(path)

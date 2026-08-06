export function focusDriverIds(ids: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const value of ids) {
    const id = value.trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    result.push(id)
    if (result.length === 2) break
  }
  return result
}

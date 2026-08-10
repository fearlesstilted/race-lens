export type DotdResultKind = 'official' | 'official-pending' | 'user' | 'race-lens'

export function dotdResultOrder(
  finished: boolean,
  official: { driver: string } | null,
  userPick: string | null,
  raceLensPick: string | null,
): DotdResultKind[] {
  const order: DotdResultKind[] = []
  if (finished) order.push(official ? 'official' : 'official-pending')
  if (userPick) order.push('user')
  if (raceLensPick) order.push('race-lens')
  return order
}

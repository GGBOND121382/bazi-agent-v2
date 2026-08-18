import type { CurrentUserDTO } from '@/api/schema'

const CURRENT_USER_KEY = 'bazi:current-user'

export function getCurrentUser(): CurrentUserDTO | null {
  try {
    const raw = sessionStorage.getItem(CURRENT_USER_KEY)
    if (!raw) return null
    const user = JSON.parse(raw) as Partial<CurrentUserDTO> | null
    if (!user || typeof user.user_id !== 'string' || !user.user_id) return null
    return user as CurrentUserDTO
  } catch {
    return null
  }
}

export function setCurrentUser(user: CurrentUserDTO): void {
  sessionStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user))
}

export function clearCurrentUser(): void {
  sessionStorage.removeItem(CURRENT_USER_KEY)
}

export function currentUserId(): string {
  return getCurrentUser()?.user_id ?? 'unauthenticated'
}

export function userStorageKey(key: string): string {
  return `bazi:user:${currentUserId()}:${key}`
}

export function chartMetaKey(chartId: string): string {
  return userStorageKey(`chart-meta:${chartId}`)
}

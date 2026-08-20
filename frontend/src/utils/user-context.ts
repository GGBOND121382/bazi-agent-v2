import type { CurrentUserDTO } from '@/api/schema'

const CURRENT_USER_KEY = 'bazi:current-user'
const AUTH_EVENT_KEY = 'bazi:auth-event'
const LEGACY_DRAFT_KEY = 'bazi:draft:birth'
const LEGACY_CHART_META_PREFIX = 'bazi:chart-meta:'

export type AuthChange = {
  user_id: string | null
  nonce: string
}

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

function storageKeyForUser(userId: string, key: string): string {
  return `bazi:user:${userId}:${key}`
}

export function userStorageKey(key: string): string {
  return storageKeyForUser(currentUserId(), key)
}

export function chartMetaKey(chartId: string): string {
  return userStorageKey(`chart-meta:${chartId}`)
}

export function authEventKey(): string {
  return AUTH_EVENT_KEY
}

export function publishAuthChange(userId: string | null): void {
  const event: AuthChange = {
    user_id: userId,
    nonce: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  }
  localStorage.setItem(AUTH_EVENT_KEY, JSON.stringify(event))
}

export function parseAuthChange(raw: string | null): AuthChange | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as Partial<AuthChange> | null
    if (!value || !('user_id' in value) || typeof value.nonce !== 'string') return null
    if (value.user_id !== null && typeof value.user_id !== 'string') return null
    return { user_id: value.user_id ?? null, nonce: value.nonce }
  } catch {
    return null
  }
}

export function migrateLegacyStorageToAdmin(user: CurrentUserDTO): number {
  if (user.role !== 'admin') return 0

  let migrated = 0
  const legacyKeys: string[] = []
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index)
    if (key === LEGACY_DRAFT_KEY || key?.startsWith(LEGACY_CHART_META_PREFIX)) {
      legacyKeys.push(key)
    }
  }

  for (const legacyKey of legacyKeys) {
    const value = localStorage.getItem(legacyKey)
    if (value === null) continue

    const scopedKey = legacyKey === LEGACY_DRAFT_KEY
      ? storageKeyForUser(user.user_id, 'draft:birth')
      : storageKeyForUser(user.user_id, `chart-meta:${legacyKey.slice(LEGACY_CHART_META_PREFIX.length)}`)

    // Existing account-scoped data is newer and wins. The unscoped legacy value
    // is still removed because legacy browser data is defined to belong to admin.
    if (localStorage.getItem(scopedKey) === null) {
      localStorage.setItem(scopedKey, value)
    }
    localStorage.removeItem(legacyKey)
    migrated += 1
  }

  return migrated
}

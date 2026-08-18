import { beforeEach, describe, expect, it } from 'vitest'
import type { CurrentUserDTO } from '@/api/schema'
import {
  chartMetaKey,
  clearCurrentUser,
  currentUserId,
  getCurrentUser,
  migrateLegacyStorageToAdmin,
  setCurrentUser,
  userStorageKey,
} from '@/utils/user-context'

function user(userId: string, role: CurrentUserDTO['role'] = 'user'): CurrentUserDTO {
  return {
    user_id: userId,
    username: userId,
    role,
    enabled: true,
    approval_status: 'approved',
    must_change_password: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('user-context', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('separates local storage namespaces by authenticated user', () => {
    setCurrentUser(user('admin-1'))
    const adminDraft = userStorageKey('draft:birth')
    const adminChart = chartMetaKey('chart-1')

    setCurrentUser(user('user-2'))
    const userDraft = userStorageKey('draft:birth')
    const userChart = chartMetaKey('chart-1')

    expect(adminDraft).toBe('bazi:user:admin-1:draft:birth')
    expect(userDraft).toBe('bazi:user:user-2:draft:birth')
    expect(adminChart).not.toBe(userChart)
  })

  it('clears and rejects malformed cached identity', () => {
    setCurrentUser(user('user-1'))
    expect(getCurrentUser()?.user_id).toBe('user-1')
    expect(currentUserId()).toBe('user-1')

    clearCurrentUser()
    expect(getCurrentUser()).toBeNull()
    expect(currentUserId()).toBe('unauthenticated')

    sessionStorage.setItem('bazi:current-user', '{bad json')
    expect(getCurrentUser()).toBeNull()
  })

  it('moves unscoped legacy browser data to admin only', () => {
    localStorage.setItem('bazi:draft:birth', '{"name":"legacy draft"}')
    localStorage.setItem('bazi:chart-meta:chart-1', '{"name":"legacy chart"}')

    expect(migrateLegacyStorageToAdmin(user('user-1'))).toBe(0)
    expect(localStorage.getItem('bazi:draft:birth')).toBeTruthy()
    expect(localStorage.getItem('bazi:chart-meta:chart-1')).toBeTruthy()

    const admin = user('admin-1', 'admin')
    expect(migrateLegacyStorageToAdmin(admin)).toBe(2)
    expect(localStorage.getItem('bazi:draft:birth')).toBeNull()
    expect(localStorage.getItem('bazi:chart-meta:chart-1')).toBeNull()
    expect(localStorage.getItem('bazi:user:admin-1:draft:birth')).toBe('{"name":"legacy draft"}')
    expect(localStorage.getItem('bazi:user:admin-1:chart-meta:chart-1')).toBe('{"name":"legacy chart"}')
  })

  it('does not overwrite newer admin-scoped data during migration', () => {
    localStorage.setItem('bazi:chart-meta:chart-1', '{"name":"legacy"}')
    localStorage.setItem('bazi:user:admin-1:chart-meta:chart-1', '{"name":"newer"}')

    expect(migrateLegacyStorageToAdmin(user('admin-1', 'admin'))).toBe(1)
    expect(localStorage.getItem('bazi:chart-meta:chart-1')).toBeNull()
    expect(localStorage.getItem('bazi:user:admin-1:chart-meta:chart-1')).toBe('{"name":"newer"}')
  })
})

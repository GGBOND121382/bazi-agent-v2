import { beforeEach, describe, expect, it } from 'vitest'
import type { CurrentUserDTO } from '@/api/schema'
import {
  chartMetaKey,
  clearCurrentUser,
  currentUserId,
  getCurrentUser,
  setCurrentUser,
  userStorageKey,
} from '@/utils/user-context'

function user(userId: string): CurrentUserDTO {
  return {
    user_id: userId,
    username: userId,
    role: 'user',
    enabled: true,
    approval_status: 'approved',
    must_change_password: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('user-context', () => {
  beforeEach(() => sessionStorage.clear())

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
})

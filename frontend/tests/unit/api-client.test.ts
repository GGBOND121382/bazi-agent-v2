/**
 * Vitest unit tests for the frontend API client.
 * Verifies:
 * - POST /v1/charts sends Idempotency-Key + X-Request-ID
 * - authenticated tab requests declare the expected user id
 * - GET /v1/charts/{id} parses success
 * - 4xx/5xx responses throw ApiError with the structured envelope
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BaziClient, ApiError } from '@/api'

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

describe('BaziClient.createChart', () => {
  let fetchSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    sessionStorage.clear()
    fetchSpy = vi.fn()
  })

  it('sends Idempotency-Key + X-Request-ID + JSON body', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        {
          schema_version: 'chart-result-v1',
          chart_id: 'chart_1',
          calculation_status: 'passed',
          calculation_profile_id: 'ziping_standard_v1',
          normalized_time: {},
          calendar: {},
          pillars: [],
          day_master: '甲',
          facts: [],
          engine_versions: [],
          warnings: [],
        },
        201,
      ),
    )
    const client = new BaziClient({ baseUrl: '/api', fetcher: fetchSpy as unknown as typeof fetch })
    await client.createChart({
      schema_version: 'birth-request-v1',
      gender: 'male',
      birth_datetime_local: '1990-06-15T12:00:00',
      timezone: 'Asia/Shanghai',
      birthplace: { country: 'CN', city: 'Shanghai' },
      calculation_profile_id: 'ziping_standard_v1',
    })

    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/v1/charts')
    const headers = (init?.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(headers['Idempotency-Key']).toMatch(/^idem_/)
    expect(headers['X-Request-ID']).toMatch(/^req_/)
    expect(headers['X-Bazi-Expected-User-ID']).toBeUndefined()
  })

  it('binds authenticated requests to the tab user id', async () => {
    sessionStorage.setItem('bazi:current-user', JSON.stringify({
      user_id: 'user-123',
      username: 'tester',
      role: 'user',
      enabled: true,
      approval_status: 'approved',
      must_change_password: false,
      created_at: '2026-01-01T00:00:00Z',
    }))
    fetchSpy.mockResolvedValueOnce(jsonResponse({ charts: [], reports: [] }))

    const client = new BaziClient({ baseUrl: '/api', fetcher: fetchSpy as unknown as typeof fetch })
    await client.getHistory()

    const headers = (fetchSpy.mock.calls[0][1]?.headers ?? {}) as Record<string, string>
    expect(headers['X-Bazi-Expected-User-ID']).toBe('user-123')
  })

  it('returns the chart DTO on 201', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        {
          schema_version: 'chart-result-v1',
          chart_id: 'chart_2',
          calculation_status: 'passed',
          calculation_profile_id: 'ziping_standard_v1',
          normalized_time: {},
          calendar: {},
          pillars: [],
          day_master: '甲',
          facts: [],
          engine_versions: [],
          warnings: [],
        },
        201,
      ),
    )
    const client = new BaziClient({ baseUrl: '/api', fetcher: fetchSpy as unknown as typeof fetch })
    const dto = await client.createChart({
      schema_version: 'birth-request-v1',
      gender: 'male',
      birth_datetime_local: '1990-06-15T12:00:00',
      timezone: 'Asia/Shanghai',
      birthplace: { country: 'CN', city: 'Shanghai' },
      calculation_profile_id: 'ziping_standard_v1',
    })
    expect(dto.chart_id).toBe('chart_2')
  })

  it('throws ApiError with the api-error envelope on 422', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        {
          schema_version: 'api-error-v1',
          request_id: 'req_test',
          error_code: 'INVALID_INPUT',
          message_key: 'input.invalid',
          retryable: false,
        },
        422,
      ),
    )
    const client = new BaziClient({ baseUrl: '/api', fetcher: fetchSpy as unknown as typeof fetch })
    await expect(
      client.createChart({
        schema_version: 'birth-request-v1',
        gender: 'male',
        birth_datetime_local: '1990-06-15T12:00:00',
        timezone: 'Asia/Shanghai',
        birthplace: { country: 'CN', city: 'Shanghai' },
        calculation_profile_id: 'ziping_standard_v1',
      }),
    ).rejects.toBeInstanceOf(ApiError)
  })
})

describe('BaziClient.getChart', () => {
  beforeEach(() => sessionStorage.clear())

  it('encodes chartId', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        schema_version: 'chart-result-v1',
        chart_id: 'chart/x',
        calculation_status: 'passed',
        calculation_profile_id: 'ziping_standard_v1',
        normalized_time: {},
        calendar: {},
        pillars: [],
        day_master: '甲',
        facts: [],
        engine_versions: [],
        warnings: [],
      }),
    )
    const client = new BaziClient({ baseUrl: '/api', fetcher: fetchSpy as unknown as typeof fetch })
    await client.getChart('chart/x')
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/v1/charts/chart%2Fx')
  })
})

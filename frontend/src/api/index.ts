/**
 * Singleton client + convenience composables.
 */
import { BaziClient } from './client'

let _client: BaziClient | null = null

export function useBaziClient(): BaziClient {
  if (!_client) _client = new BaziClient()
  return _client
}

export { BaziClient, ApiError } from './client'
export * from './schema'
export interface GuestPass {
  id: number
  guest_name: string | null
  device_id: string
  is_active: boolean
  valid_until: string
  used_count: number
  max_uses: number
}
export interface GuestCreation {
  pass_code: string
  valid_until: string
}
export interface Member {
  id: number
  username: string
  role: string
  status: string
  created_at: string
}
export interface Activity {
  id: number
  timestamp: string
  username?: string
  action?: string
  device_id?: string
  command_id?: string
  expected_username?: string
  face_user_id?: string
  passed?: boolean
  request_id?: string
  similarity_score?: number
  failure_reason?: string
  snapshot?: string | null
}
export interface Alarm {
  id: number
  time: string
  type: string
  status: string
  message: string
  handled_by: string | null
  handled_at: string | null
  email_status: string
  snapshot?: string | null
}
export interface Evidence {
  observed_at: string
  protocol: { version: string; handshake: string; envelope: string; legacy_upload_enabled: boolean }
  controls: Array<{ name: string; detail: string }>
  storage: { sessions: number; receipts: number; commands: number }
  limitations: string[]
  verification: {
    passed: boolean
    created_at: string
    environment: string
    git_sha: string
    source_digest: string
    scope: string
    checks: Array<{ name: string; exit_code: number }>
  } | null
}

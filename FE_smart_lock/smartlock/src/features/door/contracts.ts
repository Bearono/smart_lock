export interface DeviceBinding {
  device_id: string
  credential_id: number
  is_active: boolean
  created_at: string
}
export interface AuthStatus {
  devices: DeviceBinding[]
  totp_bound: boolean
  failed_attempts?: number
  is_locked?: boolean
}
export interface UnlockCredential {
  device_id: string
  unlock_token: string
}
export interface CommandAcceptance {
  command_id: string
  command_accepted: boolean
  hardware_confirmed: boolean
}
export interface TrackedCommand {
  id: string
  deviceId: string
  action: string
}

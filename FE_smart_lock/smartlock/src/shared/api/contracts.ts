/** Runtime contracts at the network boundary; never trust an HTTP type assertion. */
export interface Device {
  device_id: string
  display_name: string | null
  reported_status: 'LOCKED' | 'UNLOCKED' | 'UNKNOWN'
  camera_status: 'ONLINE' | 'OFFLINE' | 'ERROR' | 'UNKNOWN'
  is_online: boolean
  battery: number | null
  last_update: string | null
}
export interface Snapshot {
  snapshot: string | null
  received_at: string | null
  captured_at: null
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('服务返回了无效数据')
  return value as Record<string, unknown>
}
function nullableString(value: unknown): string | null {
  if (value == null) return null
  if (typeof value !== 'string') throw new Error('服务返回了无效文本')
  return value
}
export function parseDevice(value: unknown): Device {
  const item = object(value)
  if (typeof item.device_id !== 'string' || !item.device_id || typeof item.is_online !== 'boolean')
    throw new Error('设备信息不完整，请重新获取')
  const lock = ['LOCKED', 'UNLOCKED', 'UNKNOWN'].includes(String(item.reported_status))
    ? item.reported_status
    : 'UNKNOWN'
  const camera = ['ONLINE', 'OFFLINE', 'ERROR', 'UNKNOWN'].includes(String(item.camera_status))
    ? item.camera_status
    : 'UNKNOWN'
  return {
    device_id: item.device_id,
    display_name: nullableString(item.display_name),
    reported_status: lock as Device['reported_status'],
    camera_status: camera as Device['camera_status'],
    is_online: item.is_online,
    battery:
      typeof item.battery === 'number' &&
      Number.isInteger(item.battery) &&
      item.battery >= 0 &&
      item.battery <= 100
        ? item.battery
        : null,
    last_update: nullableString(item.last_update)
  }
}
export function parseDevices(value: unknown): Device[] {
  if (!Array.isArray(value)) throw new Error('设备列表格式不正确')
  return value.map(parseDevice)
}
export function parseSnapshot(value: unknown): Snapshot {
  const item = object(value),
    path = nullableString(item.snapshot)
  if (path && !/^\/api\/media\/[a-f0-9]{32}\.jpg$/.test(path)) throw new Error('快照路径不正确')
  return { snapshot: path, received_at: nullableString(item.received_at), captured_at: null }
}

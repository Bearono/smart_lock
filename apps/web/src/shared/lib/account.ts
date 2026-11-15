import { reactive } from 'vue'

export const account = reactive({ username: '', role: '', loaded: false })

// Retire credentials from older versions; never move them to another JavaScript store.
try {
  for (const key of ['token', 'username', 'role']) localStorage.removeItem(key)
} catch {
  // Storage may be disabled; current sessions do not depend on Web Storage.
}

export function setAccount(username: string, role: string) {
  Object.assign(account, { username, role, loaded: true })
}

export function clearAccount() {
  Object.assign(account, { username: '', role: '', loaded: false })
}

export async function ensureAccount() {
  if (account.loaded) return !!account.username
  try {
    const { auth } = await import('../api/index.ts')
    const { data } = await auth.session()
    setAccount(data.username, data.role)
    return true
  } catch {
    clearAccount()
    return false
  }
}

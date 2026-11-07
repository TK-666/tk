const tabSessionKey = 'art-tab-session'
let tabSession = sessionStorage.getItem(tabSessionKey)
if (!tabSession) {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  tabSession = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  sessionStorage.setItem(tabSessionKey, tabSession)
}

export async function api(path, options = {}) {
  const headers = { ...options.headers }
  headers['X-Tab-Session'] = tabSession
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`)
  return data
}

export const json = (method, body) => ({ method, body: JSON.stringify(body) })

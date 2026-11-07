export async function api(path, options = {}) {
  const headers = { ...options.headers }
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`)
  return data
}

export const json = (method, body) => ({ method, body: JSON.stringify(body) })

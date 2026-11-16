'use strict'
;(() => {
  const storageKey = 'smartlock.simulator.viewer'
  const pollInterval = 1200
  const elements = Object.fromEntries(
    [
      'status-title',
      'status-detail',
      'connection-label',
      'received-at',
      'architecture',
      'fault-tag',
      'authorization-help',
      'latest-content',
      'latest-empty',
      'latest-result',
      'latest-target',
      'latest-time',
      'latest-id',
      'latest-indicator',
      'history',
      'history-empty',
      'history-count',
      'fullscreen-toggle',
      'fullscreen-label',
      'screenreader-announcement'
    ].map((id) => [id, document.getElementById(id)])
  )
  const stateNames = {
    LOCKED: '已上锁',
    UNLOCKED: '已解锁',
    UNKNOWN: '状态未知'
  }
  const stateDetails = {
    LOCKED: '锁舌伸出',
    UNLOCKED: '锁舌收回',
    UNKNOWN: '等待状态反馈'
  }
  const faultNames = { jammed: '锁舌卡住', feedback_lost: '反馈丢失' }
  const clockFormat = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
  const dateFormat = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' })
  let token = ''
  let timer
  let controller
  let lastSnapshot = null
  let renderedHistory = ''
  let initialized = false
  let credentialVersion = 0
  let refreshPending = false

  document.body.dataset.initialized = 'false'

  function readToken() {
    const fragment = new URLSearchParams(location.hash.slice(1))
    const supplied = fragment.get('token')
    if (location.hash) history.replaceState(null, '', `${location.pathname}${location.search}`)
    try {
      if (supplied) sessionStorage.setItem(storageKey, supplied)
      return supplied || sessionStorage.getItem(storageKey) || ''
    } catch {
      return supplied || ''
    }
  }

  function clearToken() {
    token = ''
    try {
      sessionStorage.removeItem(storageKey)
    } catch {
      /* Private browsing may disable storage. */
    }
  }

  function timeLabel(timestamp) {
    return typeof timestamp === 'number' && Number.isFinite(timestamp)
      ? clockFormat.format(new Date(timestamp * 1000))
      : '时间未记录'
  }

  function setText(id, value) {
    if (elements[id].textContent !== value) elements[id].textContent = value
  }

  function commandTime(timestamp) {
    if (timestamp === null) return '时间未记录'
    const date = new Date(timestamp * 1000)
    const now = new Date()
    const time = timeLabel(timestamp)
    return date.toDateString() === now.toDateString() ? time : `${dateFormat.format(date)} ${time}`
  }

  function validTimestamp(value) {
    return typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 8640000000000
  }

  function commandIcon(command) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.setAttribute('viewBox', '0 0 24 24')
    svg.setAttribute('aria-hidden', 'true')
    const path = document.createElementNS(svg.namespaceURI, 'path')
    path.setAttribute(
      'd',
      command.status === 'failed'
        ? 'm8 8 8 8m0-8-8 8'
        : command.target_status === 'UNLOCKED'
          ? 'M8 10V7a4 4 0 0 1 7.5-2M6 10h12v11H6Zm6 5v2'
          : 'M8 10V7a4 4 0 0 1 8 0v3M6 10h12v11H6Zm6 5v2'
    )
    svg.append(path)
    return svg
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag)
    element.className = className
    element.textContent = text
    return element
  }

  function renderCommands(commands) {
    const signature = `${new Date().toDateString()}:${JSON.stringify(commands)}`
    if (renderedHistory === signature) return
    renderedHistory = signature
    const latest = commands[0]
    elements['latest-empty'].hidden = Boolean(latest)
    elements['latest-content'].hidden = !latest
    elements['history-empty'].hidden = Boolean(latest)
    if (latest) {
      elements['latest-result'].textContent = latest.status === 'executed' ? '执行成功' : '执行失败'
      elements['latest-result'].dataset.result = latest.status
      elements['latest-indicator'].dataset.result = latest.status
      elements['latest-target'].textContent = latest.target_status === 'LOCKED' ? '上锁' : '解锁'
      elements['latest-time'].textContent = commandTime(latest.executed_at)
      elements['latest-id'].textContent = latest.id
      if (latest.executed_at !== null)
        elements['latest-time'].dateTime = new Date(latest.executed_at * 1000).toISOString()
      else elements['latest-time'].removeAttribute('datetime')
    } else {
      delete elements['latest-indicator'].dataset.result
    }
    const fragment = document.createDocumentFragment()
    for (const command of commands) {
      const item = document.createElement('li')
      item.className = 'history-item'
      item.dataset.commandId = command.id
      item.dataset.target = command.target_status
      item.dataset.result = command.status
      const icon = textElement('span', 'history-icon', '')
      icon.append(commandIcon(command))
      const description = textElement('span', 'history-description', '')
      const identity = textElement('code', 'history-identity', command.id.slice(0, 8))
      identity.title = command.id
      description.append(
        textElement('span', 'history-action', command.target_status === 'LOCKED' ? '上锁' : '解锁'),
        identity
      )
      const outcome = textElement('span', 'history-outcome', '')
      const time = textElement('time', 'history-time', commandTime(command.executed_at))
      if (command.executed_at !== null)
        time.dateTime = new Date(command.executed_at * 1000).toISOString()
      outcome.append(
        textElement('span', 'history-result', command.status === 'executed' ? '成功' : '失败'),
        time
      )
      item.append(icon, description, outcome)
      fragment.append(item)
    }
    elements.history.replaceChildren(fragment)
  }

  function validSnapshot(snapshot) {
    const validStates = ['LOCKED', 'UNLOCKED', 'UNKNOWN']
    return (
      snapshot &&
      snapshot.execution_mode === 'SIMULATED' &&
      validStates.includes(snapshot.reported_status) &&
      ['normal', 'jammed', 'feedback_lost'].includes(snapshot.fault) &&
      (snapshot.fault !== 'feedback_lost' || snapshot.reported_status === 'UNKNOWN') &&
      validTimestamp(snapshot.observed_at) &&
      typeof snapshot.architecture === 'string' &&
      Number.isInteger(snapshot.command_count) &&
      snapshot.command_count >= 0 &&
      Array.isArray(snapshot.commands) &&
      snapshot.commands.length <= 8 &&
      snapshot.commands.every(
        (command) =>
          command &&
          /^[0-9a-f]{32}$/.test(command.id) &&
          ['LOCKED', 'UNLOCKED'].includes(command.target_status) &&
          validStates.includes(command.reported_status) &&
          ['executed', 'failed'].includes(command.status) &&
          (command.status === 'executed') === (command.target_status === command.reported_status) &&
          (command.executed_at === null || validTimestamp(command.executed_at))
      )
    )
  }

  function renderSnapshot(snapshot) {
    const changed = lastSnapshot && snapshot.commands[0]?.id !== lastSnapshot.commands[0]?.id
    lastSnapshot = snapshot
    document.body.dataset.connection = 'online'
    document.body.dataset.state = snapshot.reported_status
    setText('status-title', stateNames[snapshot.reported_status])
    setText('status-detail', stateDetails[snapshot.reported_status])
    elements['connection-label'].textContent = '实时连接'
    elements['received-at'].textContent = `已同步 ${timeLabel(snapshot.observed_at)}`
    elements['authorization-help'].hidden = true
    elements['architecture'].hidden = !snapshot.architecture
    elements['architecture'].textContent =
      snapshot.architecture === 'aarch64' ? 'ARM64' : snapshot.architecture.toUpperCase()
    elements['fault-tag'].hidden = snapshot.fault === 'normal'
    setText('fault-tag', faultNames[snapshot.fault] || '')
    elements['history-count'].textContent = String(snapshot.commands.length)
    elements['history-count'].title = `当前保留 ${snapshot.command_count} 条命令`
    renderCommands(snapshot.commands)
    if (changed && snapshot.commands[0]) {
      const latest = snapshot.commands[0]
      elements['screenreader-announcement'].textContent =
        `${latest.target_status === 'LOCKED' ? '上锁' : '解锁'}${latest.status === 'executed' ? '执行成功' : '执行失败'}`
    }
    if (!initialized) {
      initialized = true
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          document.body.dataset.initialized = 'true'
        })
      )
    }
  }

  function unavailable(unauthorized = false) {
    document.body.dataset.connection = unauthorized ? 'unauthorized' : 'offline'
    elements['connection-label'].textContent = unauthorized ? '未授权连接' : '等待重连'
    setText('status-title', unauthorized ? '尚未连接' : '连接中断')
    setText(
      'status-detail',
      lastSnapshot ? `上次状态 · ${stateNames[lastSnapshot.reported_status]}` : '尚未取得门锁状态'
    )
    elements['authorization-help'].hidden = !unauthorized
    if (lastSnapshot)
      elements['received-at'].textContent = `上次接收 ${timeLabel(lastSnapshot.observed_at)}`
  }

  async function poll() {
    clearTimeout(timer)
    if (!token || document.hidden || controller) return
    controller = new AbortController()
    const version = credentialVersion
    const timeout = setTimeout(() => controller?.abort(), 8000)
    try {
      const response = await fetch('/panel/state', {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json'
        },
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
        signal: controller.signal
      })
      if (version !== credentialVersion) return
      if (response.status === 401 || response.status === 403) {
        clearToken()
        unavailable(true)
        return
      }
      if (!response.ok) throw new Error('Panel state unavailable')
      const snapshot = await response.json()
      if (version !== credentialVersion) return
      if (!validSnapshot(snapshot)) throw new Error('Invalid simulator state')
      renderSnapshot(snapshot)
    } catch {
      if (!document.hidden && version === credentialVersion) unavailable()
    } finally {
      clearTimeout(timeout)
      controller = null
      if (token && !document.hidden) timer = setTimeout(poll, refreshPending ? 0 : pollInterval)
      refreshPending = false
    }
  }

  window.addEventListener('hashchange', () => {
    token = readToken()
    credentialVersion += 1
    clearTimeout(timer)
    if (controller) {
      refreshPending = true
      controller.abort()
    } else if (token) poll()
    if (!token) unavailable(true)
  })

  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer)
    if (document.hidden) controller?.abort()
    else poll()
  })
  window.addEventListener('pagehide', () => {
    clearTimeout(timer)
    controller?.abort()
  })
  window.addEventListener('pageshow', () => {
    if (token) poll()
  })

  elements['fullscreen-toggle'].hidden = !document.fullscreenEnabled
  elements['fullscreen-toggle'].addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await document.documentElement.requestFullscreen()
    } catch {
      elements['screenreader-announcement'].textContent = '浏览器暂不支持全屏'
    }
  })
  document.addEventListener('fullscreenchange', () => {
    const label = document.fullscreenElement ? '退出全屏' : '全屏'
    elements['fullscreen-toggle'].setAttribute('aria-label', label)
    elements['fullscreen-label'].textContent = label
  })

  token = readToken()
  if (token) poll()
  else unavailable(true)
})()

'use strict'

const fs = require('node:fs')
const path = require('node:path')
const { Client } = require('douyudm')

const roomId = Number.parseInt(process.env.ROOM_ID || '6657', 10)
const outputPath = path.resolve(process.env.LIVE_JSONL_PATH || path.join(__dirname, '..', 'data', 'live.jsonl'))
const maxRuntimeSeconds = process.env.COLLECTOR_MAX_SECONDS == null
  ? null
  : Number.parseInt(process.env.COLLECTOR_MAX_SECONDS, 10)
const sessionId = process.env.SESSION_ID || null

if (!Number.isInteger(roomId) || roomId <= 0) {
  throw new Error('ROOM_ID must be a positive integer')
}
if (maxRuntimeSeconds !== null && (!Number.isInteger(maxRuntimeSeconds) || maxRuntimeSeconds <= 0)) {
  throw new Error('COLLECTOR_MAX_SECONDS must be a positive integer when set')
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true })

let received = 0
let shuttingDown = false
let client = null

async function resolveRoomId(configuredRoomId) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)
  try {
    const response = await fetch(`https://m.douyu.com/${configuredRoomId}`, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      signal: controller.signal
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const html = await response.text()
    const match = html.match(/"rid"\s*:\s*(\d+)/)
    if (!match) {
      throw new Error('real room ID was not found in the page data')
    }
    const resolvedRoomId = Number.parseInt(match[1], 10)
    if (!Number.isInteger(resolvedRoomId) || resolvedRoomId <= 0) {
      throw new Error('resolved room ID is invalid')
    }
    return resolvedRoomId
  } finally {
    clearTimeout(timeout)
  }
}

function stop(signal) {
  if (shuttingDown) return
  shuttingDown = true
  console.log(`[collector] ${signal} received; exiting`)
  client?.close()
  process.exit(0)
}

process.on('SIGINT', () => stop('SIGINT'))
process.on('SIGTERM', () => stop('SIGTERM'))

async function main() {
  let resolvedRoomId = roomId
  try {
    resolvedRoomId = await resolveRoomId(roomId)
  } catch (error) {
    console.warn(`[collector] could not resolve roomId=${roomId}; using it directly (${error?.message || error})`)
  }

  client = new Client(resolvedRoomId, { ignore: ['uenter', 'spbc', 'gdp', 'rss'] })
  client.on('connect', (connectedClient) => {
    console.log(`[collector] connected roomId=${roomId} resolvedRoomId=${connectedClient.roomId}`)
  })
  client.on('loginres', () => {
    console.log('[collector] logged in')
  })

  client.on('chatmsg', (message) => {
    const text = typeof message.txt === 'string' ? message.txt : ''
    if (!text) return
    const record = {
      ts: new Date().toISOString(),
      roomId,
      sessionId,
      uid: message.uid == null ? null : String(message.uid),
      text
    }
    fs.appendFileSync(outputPath, `${JSON.stringify(record)}\n`, 'utf8')
    received += 1
    if (received % 50 === 0) {
      console.log(`[collector] received=${received} written=${received}`)
    }
  })

  client.on('error', (connectedClient, error) => {
    console.error(`[collector] connection error roomId=${connectedClient.roomId}: ${error?.message || error}`)
  })

  client.on('disconnect', (connectedClient) => {
    if (!shuttingDown) {
      console.error(`[collector] disconnected resolvedRoomId=${connectedClient.roomId}; restarting supervisor will reconnect`)
      process.exit(1)
    }
  })

  if (maxRuntimeSeconds !== null) {
    setTimeout(() => stop('runtime limit'), maxRuntimeSeconds * 1000).unref()
  }
  client.run()
}

main().catch((error) => {
  console.error(`[collector] failed: ${error?.message || error}`)
  process.exit(1)
})

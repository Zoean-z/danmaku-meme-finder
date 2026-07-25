'use strict'

const { spawn } = require('node:child_process')
const path = require('node:path')

const collectorPath = path.join(__dirname, 'collector.js')
const restartDelayMs = 2000
let child = null
let stopping = false

function launch() {
  child = spawn(process.execPath, [collectorPath], {
    cwd: path.resolve(__dirname, '..'),
    env: process.env,
    stdio: 'inherit'
  })
  child.once('exit', (code, signal) => {
    if (stopping) process.exit(code || 0)
    console.error(`[supervisor] collector exited code=${code} signal=${signal}; restarting in ${restartDelayMs}ms`)
    setTimeout(launch, restartDelayMs)
  })
}

function stop(signal) {
  stopping = true
  if (child) child.kill(signal)
  else process.exit(0)
}

process.on('SIGINT', () => stop('SIGINT'))
process.on('SIGTERM', () => stop('SIGTERM'))
launch()

/**
 * Start vite preview against dist/, run pa11y-ci, then stop the server.
 * Requires: npm run build (dist/ must exist).
 */
import { spawn } from 'node:child_process'
import { existsSync, writeFileSync, unlinkSync } from 'node:fs'
import { setTimeout as sleep } from 'node:timers/promises'

const PORT = Number(process.env.PA11Y_PORT || 4188)
const HOST = process.env.PA11Y_HOST || '127.0.0.1'
const BASE = `http://${HOST}:${PORT}`

const PATHS = ['/login', '/signup', '/how-it-works']

if (!existsSync('dist/index.html')) {
  console.error('Missing dist/index.html — run `npm run build` first.')
  process.exit(1)
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: 'inherit', shell: true, ...opts })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`${cmd} ${args.join(' ')} exited with code ${code}`))
    })
  })
}

async function waitForServer(maxMs = 90000) {
  const start = Date.now()
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(`${BASE}/login`)
      if (res.ok) return
    } catch {
      /* not ready */
    }
    await sleep(500)
  }
  throw new Error(`Preview server did not become ready at ${BASE}`)
}

function writePa11yConfig() {
  const config = {
    defaults: {
      standard: 'WCAG2AA',
      timeout: 90000,
      wait: 2000,
      runners: ['axe'],
      chromeLaunchConfig: {
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
      },
      hideElements: '.mapboxgl-map, .mapboxgl-canvas, iframe[src*="mapbox"]',
    },
    urls: PATHS.map((p) => `${BASE}${p}`),
  }
  const file = '.pa11yci.generated.json'
  writeFileSync(file, `${JSON.stringify(config, null, 2)}\n`)
  return file
}

const preview = spawn(
  'npx',
  ['vite', 'preview', '--port', String(PORT), '--host', HOST, '--strictPort'],
  { stdio: ['ignore', 'pipe', 'pipe'], shell: true },
)

let previewLog = ''
preview.stdout?.on('data', (d) => { previewLog += d.toString() })
preview.stderr?.on('data', (d) => { previewLog += d.toString() })

const killPreview = () => {
  if (!preview.killed) {
    try { preview.kill('SIGTERM') } catch { /* noop */ }
  }
}

process.on('SIGINT', () => { killPreview(); process.exit(130) })
process.on('SIGTERM', () => { killPreview(); process.exit(143) })

let configFile = ''
try {
  console.log(`Waiting for preview at ${BASE} …`)
  await waitForServer()
  configFile = writePa11yConfig()
  console.log(`Preview ready — running pa11y-ci on ${PATHS.join(', ')} …`)
  await run('npx', ['pa11y-ci', '--config', configFile])
  console.log('pa11y-ci finished — review any reported issues above.')
} catch (err) {
  console.error(err.message || err)
  if (previewLog) console.error('Preview log:\n', previewLog.slice(-2000))
  process.exitCode = 1
} finally {
  killPreview()
  if (configFile && existsSync(configFile)) {
    try { unlinkSync(configFile) } catch { /* noop */ }
  }
}

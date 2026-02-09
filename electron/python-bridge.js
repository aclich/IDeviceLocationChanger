/**
 * Python Bridge - Manages the Python backend process
 *
 * Simplified version that only:
 * 1. Spawns the Python HTTP server
 * 2. Waits for it to be ready
 * 3. Stops it on shutdown
 *
 * All communication (HTTP + SSE) happens directly from the frontend.
 */

const { spawn, execSync } = require('child_process');
const { EventEmitter } = require('events');
const path = require('path');
const fs = require('fs');

class PythonBridge extends EventEmitter {
  constructor() {
    super();
    this.process = null;
    this.port = 8765;
    this.host = '127.0.0.1';
  }

  /**
   * Start the Python backend HTTP server
   */
  async start() {
    const pythonPath = this.findPython();
    const backendPath = path.join(__dirname, '../backend/main.py');

    console.log(`[PythonBridge] Starting backend: ${pythonPath} ${backendPath}`);
    console.log(`[PythonBridge] Server will listen on http://${this.host}:${this.port}`);

    // Start Python in HTTP mode
    this.process = spawn(pythonPath, [backendPath, '--host', this.host, '--port', String(this.port)], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    // Log stderr (Python logs)
    this.process.stderr.on('data', (data) => {
      const lines = data.toString().trim().split('\n');
      lines.forEach((line) => {
        if (line) console.log(`[Python] ${line}`);
      });
    });

    // Log stdout (should be minimal in HTTP mode)
    this.process.stdout.on('data', (data) => {
      const lines = data.toString().trim().split('\n');
      lines.forEach((line) => {
        if (line) console.log(`[Python] ${line}`);
      });
    });

    this.process.on('exit', (code, signal) => {
      console.log(`[PythonBridge] Process exited (code=${code}, signal=${signal})`);
      this.emit('exit', code);
    });

    this.process.on('error', (err) => {
      console.error('[PythonBridge] Process error:', err);
      this.emit('error', err);
    });

    // Wait for server to be ready
    await this._waitForServer();
    console.log('[PythonBridge] Backend ready');
  }

  /**
   * Wait for the HTTP server to respond to health checks
   */
  async _waitForServer(timeout = 15000) {
    const start = Date.now();
    const url = `http://${this.host}:${this.port}/health`;

    while (Date.now() - start < timeout) {
      try {
        const response = await fetch(url);
        if (response.ok) {
          return;
        }
      } catch {
        // Server not ready yet
      }

      // Check if process died
      if (this.process && this.process.exitCode !== null) {
        throw new Error(`Python process exited with code ${this.process.exitCode}`);
      }

      await new Promise((r) => setTimeout(r, 100));
    }

    throw new Error(`Backend failed to start within ${timeout}ms`);
  }

  /**
   * Get the backend URL
   */
  getUrl() {
    return `http://${this.host}:${this.port}`;
  }

  /**
   * Stop the Python backend
   */
  stop() {
    if (this.process) {
      console.log('[PythonBridge] Stopping backend...');

      // Try graceful shutdown first
      this.process.kill('SIGTERM');

      // Force kill after timeout
      setTimeout(() => {
        if (this.process && this.process.exitCode === null) {
          console.log('[PythonBridge] Force killing backend...');
          this.process.kill('SIGKILL');
        }
      }, 3000);

      this.process = null;
    }
  }

  /**
   * Find a working Python installation with pymobiledevice3
   */
  findPython() {
    const candidates = [];

    // Check asdf installs directly
    if (process.env.HOME) {
      const asdfInstalls = path.join(process.env.HOME, '.asdf/installs/python');
      try {
        if (fs.existsSync(asdfInstalls)) {
          const versions = fs.readdirSync(asdfInstalls);
          versions.sort().reverse();
          for (const ver of versions) {
            candidates.push(path.join(asdfInstalls, ver, 'bin/python3'));
          }
        }
      } catch {
        // Ignore errors
      }

      // Check pyenv installs
      const pyenvInstalls = path.join(process.env.HOME, '.pyenv/versions');
      try {
        if (fs.existsSync(pyenvInstalls)) {
          const versions = fs.readdirSync(pyenvInstalls);
          versions.sort().reverse();
          for (const ver of versions) {
            candidates.push(path.join(pyenvInstalls, ver, 'bin/python3'));
          }
        }
      } catch {
        // Ignore errors
      }
    }

    // Standard system paths
    candidates.push(
      '/opt/homebrew/bin/python3', // Homebrew on Apple Silicon
      '/usr/local/bin/python3', // Homebrew on Intel Mac
      '/usr/bin/python3', // System Python
      'python3' // PATH lookup
    );

    for (const pythonPath of candidates) {
      try {
        // Skip if file doesn't exist (except for bare 'python3')
        if (pythonPath !== 'python3' && !fs.existsSync(pythonPath)) {
          continue;
        }

        // Test if Python has pymobiledevice3
        const result = execSync(`"${pythonPath}" -c "import pymobiledevice3; print('ok')"`, {
          timeout: 5000,
          stdio: ['pipe', 'pipe', 'pipe'],
        });

        if (result.toString().includes('ok')) {
          console.log(`[PythonBridge] Found Python with pymobiledevice3: ${pythonPath}`);
          return pythonPath;
        }
      } catch {
        // This Python doesn't work, try next
      }
    }

    console.warn('[PythonBridge] Could not find Python with pymobiledevice3, using python3');
    return 'python3';
  }
}

module.exports = PythonBridge;

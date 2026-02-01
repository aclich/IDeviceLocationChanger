const { spawn } = require('child_process');
const { EventEmitter } = require('events');
const path = require('path');
const readline = require('readline');

class PythonBridge extends EventEmitter {
  constructor() {
    super();
    this.process = null;
    this.pendingRequests = new Map();
    this.requestId = 0;
  }

  async start() {
    const pythonPath = this.findPython();
    const backendPath = path.join(__dirname, '../python-backend/main.py');

    console.log(`Starting Python backend: ${pythonPath} ${backendPath}`);

    this.process = spawn(pythonPath, [backendPath], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    // Read stdout line by line
    const rl = readline.createInterface({
      input: this.process.stdout,
      crlfDelay: Infinity,
    });

    rl.on('line', (line) => {
      try {
        const message = JSON.parse(line);

        if (message.id && this.pendingRequests.has(message.id)) {
          // Response to a request
          const { resolve } = this.pendingRequests.get(message.id);
          this.pendingRequests.delete(message.id);
          resolve(message);
        } else if (message.event) {
          // Event from backend
          this.emit('event', message);
        }
      } catch (e) {
        console.error('Failed to parse backend message:', line);
      }
    });

    // Log stderr for debugging
    this.process.stderr.on('data', (data) => {
      console.log('[Python]', data.toString().trim());
    });

    this.process.on('exit', (code) => {
      console.log(`Python backend exited with code ${code}`);
      this.emit('exit', code);
    });

    this.process.on('error', (err) => {
      console.error('Python process error:', err);
      this.emit('error', err);
    });

    // Wait a bit for process to start
    return new Promise((resolve) => setTimeout(resolve, 500));
  }

  send(request) {
    return new Promise((resolve, reject) => {
      if (!this.process) {
        return reject(new Error('Python backend not running'));
      }

      const id = `req_${++this.requestId}`;
      const fullRequest = { ...request, id };

      this.pendingRequests.set(id, { resolve, reject });

      // Send request to Python via stdin
      this.process.stdin.write(JSON.stringify(fullRequest) + '\n');

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error('Request timeout'));
        }
      }, 30000);
    });
  }

  stop() {
    if (this.process) {
      console.log('Stopping Python backend...');
      this.process.kill();
      this.process = null;
    }
  }

  findPython() {
    const { execSync } = require('child_process');
    const fs = require('fs');
    const pathModule = require('path');

    const candidates = [];

    // Check asdf installs directly (not shims - shims can have issues on macOS)
    if (process.env.HOME) {
      const asdfInstalls = pathModule.join(process.env.HOME, '.asdf/installs/python');
      try {
        if (fs.existsSync(asdfInstalls)) {
          const versions = fs.readdirSync(asdfInstalls);
          // Sort versions descending to prefer newer Python
          versions.sort().reverse();
          for (const ver of versions) {
            candidates.push(pathModule.join(asdfInstalls, ver, 'bin/python3'));
          }
        }
      } catch (e) {
        // Ignore errors reading asdf directory
      }

      // Also check pyenv installs directly
      const pyenvInstalls = pathModule.join(process.env.HOME, '.pyenv/versions');
      try {
        if (fs.existsSync(pyenvInstalls)) {
          const versions = fs.readdirSync(pyenvInstalls);
          versions.sort().reverse();
          for (const ver of versions) {
            candidates.push(pathModule.join(pyenvInstalls, ver, 'bin/python3'));
          }
        }
      } catch (e) {
        // Ignore errors reading pyenv directory
      }
    }

    // Add standard system paths
    candidates.push(
      '/opt/homebrew/bin/python3',  // Homebrew on Apple Silicon
      '/usr/local/bin/python3',      // Homebrew on Intel Mac
      '/usr/bin/python3',            // System Python
      'python3'                       // Last resort: PATH lookup
    );

    for (const pythonPath of candidates) {
      try {
        // Skip if file doesn't exist (except for bare 'python3')
        if (pythonPath !== 'python3' && !fs.existsSync(pythonPath)) {
          continue;
        }

        // Test if Python exists and has pymobiledevice3
        const result = execSync(
          `"${pythonPath}" -c "import pymobiledevice3; print('ok')"`,
          { timeout: 5000, stdio: ['pipe', 'pipe', 'pipe'] }
        );
        if (result.toString().includes('ok')) {
          console.log(`Found working Python with pymobiledevice3: ${pythonPath}`);
          return pythonPath;
        }
      } catch (e) {
        // This Python doesn't work, try next
      }
    }

    console.warn('Could not find Python with pymobiledevice3, falling back to python3');
    return 'python3';
  }
}

module.exports = PythonBridge;

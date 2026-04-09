#!/usr/bin/env node
/**
 * Start script with mock data enabled
 */
process.env.MOCK_DATA = 'true';
process.env.NODE_ENV = process.env.NODE_ENV || 'development';

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const electronPath = join(__dirname, 'node_modules', '.bin', 'electron.CMD');
const mainScript = join(__dirname, 'packages', 'main', 'dist', 'index.js');

console.log('[start-mock] Starting with MOCK_DATA=true');

const child = spawn(electronPath, [mainScript], {
  stdio: 'inherit',
  env: process.env
});

child.on('exit', (code) => {
  process.exit(code);
});

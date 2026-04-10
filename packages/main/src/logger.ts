/**
 * File-based logger for the Electron main process.
 *
 * Logs are written to the userData directory under the "logs" folder.
 * Each day gets a new log file (app-YYYY-MM-DD.log).
 * Logs are also output to console for development convenience.
 */
import { app } from "electron";
import { join } from "node:path";
import { homedir } from "node:os";
import { existsSync, mkdirSync, appendFileSync, createWriteStream, WriteStream } from "node:fs";
import { format } from "node:util";

export interface Logger {
  info(message: string, ...args: unknown[]): void;
  warn(message: string, ...args: unknown[]): void;
  error(message: string, ...args: unknown[]): void;
  debug(message: string, ...args: unknown[]): void;
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  pid: number;
}

let globalLogger: FileLogger | null = null;

/**
 * Resolve the log directory path.
 * Uses app.getPath("userData") when available, falls back to ~/.polymarket-trader/logs
 */
function resolveLogDir(): string {
  try {
    const userData = app.getPath("userData");
    return join(userData, "logs");
  } catch {
    return join(homedir(), ".polymarket-trader", "logs");
  }
}

/**
 * Get today's log file path.
 */
function getLogFilePath(logDir: string): string {
  const date = new Date().toISOString().split("T")[0];
  return join(logDir, `app-${date}.log`);
}

/**
 * Format a log entry as a line.
 */
function formatLogEntry(entry: LogEntry): string {
  return `[${entry.timestamp}] [${entry.level.toUpperCase()}] [pid:${entry.pid}] ${entry.message}\n`;
}

/**
 * File-based logger that writes to both file and console.
 */
class FileLogger implements Logger {
  private logDir: string;
  private currentLogFile: string;
  private writeStream: WriteStream | null = null;
  private pid: number;
  private consoleOutput: boolean;

  constructor(options: { consoleOutput?: boolean } = {}) {
    this.logDir = resolveLogDir();
    this.currentLogFile = getLogFilePath(this.logDir);
    this.pid = process.pid;
    this.consoleOutput = options.consoleOutput ?? true;

    this.ensureLogDir();
    this.openStream();

    // Handle process exit to close stream
    process.on("exit", () => this.close());
    process.on("SIGINT", () => this.close());
    process.on("SIGTERM", () => this.close());

    // Handle uncaught exceptions
    process.on("uncaughtException", (err) => {
      this.error("Uncaught exception:", err);
      this.close();
      process.exit(1);
    });

    // Handle unhandled rejections
    process.on("unhandledRejection", (reason) => {
      this.error("Unhandled rejection:", reason);
    });
  }

  private ensureLogDir(): void {
    if (!existsSync(this.logDir)) {
      mkdirSync(this.logDir, { recursive: true });
    }
  }

  private openStream(): void {
    this.ensureLogDir();
    this.writeStream = createWriteStream(this.currentLogFile, { flags: "a" });
  }

  private checkRotation(): void {
    const expectedLogFile = getLogFilePath(this.logDir);
    if (expectedLogFile !== this.currentLogFile) {
      // Day has changed, rotate log file
      this.close();
      this.currentLogFile = expectedLogFile;
      this.openStream();
    }
  }

  private write(level: string, message: string, args: unknown[]): void {
    this.checkRotation();

    const formattedMessage = args.length > 0 ? format(message, ...args) : message;
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message: formattedMessage,
      pid: this.pid,
    };

    const line = formatLogEntry(entry);

    // Write to file
    if (this.writeStream) {
      this.writeStream.write(line);
    }

    // Also output to console
    if (this.consoleOutput) {
      const consoleMethod = level === "error" ? console.error :
                           level === "warn" ? console.warn :
                           level === "debug" ? console.debug : console.log;
      consoleMethod(`[${level.toUpperCase()}]`, formattedMessage);
    }
  }

  info(message: string, ...args: unknown[]): void {
    this.write("info", message, args);
  }

  warn(message: string, ...args: unknown[]): void {
    this.write("warn", message, args);
  }

  error(message: string, ...args: unknown[]): void {
    this.write("error", message, args);
  }

  debug(message: string, ...args: unknown[]): void {
    this.write("debug", message, args);
  }

  close(): void {
    if (this.writeStream) {
      this.writeStream.end();
      this.writeStream = null;
    }
  }

  /**
   * Get the current log directory path.
   */
  getLogDir(): string {
    return this.logDir;
  }

  /**
   * Get the current log file path.
   */
  getCurrentLogFile(): string {
    return this.currentLogFile;
  }
}

/**
 * Initialize the global logger. Should be called once at app startup.
 */
export function initLogger(options?: { consoleOutput?: boolean }): FileLogger {
  if (!globalLogger) {
    globalLogger = new FileLogger(options);
  }
  return globalLogger;
}

/**
 * Get the global logger instance.
 * If not initialized, creates a default logger.
 */
export function getLogger(): FileLogger {
  if (!globalLogger) {
    globalLogger = new FileLogger();
  }
  return globalLogger;
}

/**
 * Close the global logger and clean up resources.
 */
export function closeLogger(): void {
  if (globalLogger) {
    globalLogger.close();
    globalLogger = null;
  }
}

/**
 * Get the log directory path without initializing the logger.
 */
export function getLogDir(): string {
  return resolveLogDir();
}

/**
 * Read the latest log file content.
 * Returns empty string if no log file exists.
 */
export function readLatestLogs(maxLines: number = 500): string {
  try {
    const { readFileSync } = require("node:fs");
    const logFile = getLogFilePath(resolveLogDir());

    if (!existsSync(logFile)) {
      return "";
    }

    const content = readFileSync(logFile, "utf-8");
    const lines = content.split("\n").filter(line => line.trim());

    if (lines.length <= maxLines) {
      return content;
    }

    return lines.slice(-maxLines).join("\n") + "\n";
  } catch (err) {
    console.error("Failed to read logs:", err);
    return "";
  }
}

/**
 * List all available log files with their sizes and dates.
 */
export function listLogFiles(): Array<{ name: string; path: string; size: number; date: string }> {
  try {
    const { readdirSync, statSync } = require("node:fs");
    const logDir = resolveLogDir();

    if (!existsSync(logDir)) {
      return [];
    }

    const files = readdirSync(logDir)
      .filter((f: string) => f.endsWith(".log"))
      .map((f: string) => {
        const filePath = join(logDir, f);
        const stats = statSync(filePath);
        return {
          name: f,
          path: filePath,
          size: stats.size,
          date: stats.mtime.toISOString(),
        };
      })
      .sort((a: { date: string }, b: { date: string }) => new Date(b.date).getTime() - new Date(a.date).getTime());

    return files;
  } catch (err) {
    console.error("Failed to list log files:", err);
    return [];
  }
}

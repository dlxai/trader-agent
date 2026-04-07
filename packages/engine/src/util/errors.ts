/** Thrown when the system must enter safe mode (stop new orders). */
export class SafeModeError extends Error {
  constructor(message: string, public readonly cause: unknown) {
    super(message);
    this.name = "SafeModeError";
  }
}

/** Thrown when an incoming Polymarket event is malformed and unsafe to process. */
export class InvalidEventError extends Error {
  constructor(message: string, public readonly event: unknown) {
    super(message);
    this.name = "InvalidEventError";
  }
}

/** Thrown when Analyzer agent returns an unparseable or invalid verdict. */
export class VerdictParseError extends Error {
  constructor(message: string, public readonly raw: unknown) {
    super(message);
    this.name = "VerdictParseError";
  }
}

/** Thrown when LLM call exceeds configured timeout. */
export class LlmTimeoutError extends Error {
  constructor(public readonly timeoutMs: number) {
    super(`LLM call exceeded ${timeoutMs}ms timeout`);
    this.name = "LlmTimeoutError";
  }
}

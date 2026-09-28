/**
 * Shared mutable client state. Modules read/write this instead of globals.
 * Keep fields here; put behavior in focused modules.
 */
export const store = {
  ws: null,
  sessionId: null,
  recording: false,
  starting: false,
  stopping: false,
  turnLocked: false,

  /** @type {Float32Array[]} */
  pcmChunks: [],
  audioCtx: null,
  recStream: null,
  processor: null,
  sourceNode: null,

  /** @type {Uint8Array[]} */
  ttsChunks: [],
  /** @type {{ chunks: Uint8Array[], text: string }[]} */
  ttsPlayQueue: [],
  ttsPlaying: false,
  ttsPendingText: "",
  assistantTurnText: "",
  /** Typewriter: displayed length chasing assistantTurnText. */
  typeToken: 0,
  typeTimer: null,
  turnAwaitingIdle: false,
  /** @type {{ chunks: Uint8Array[], text: string }[]} */
  lastTtsSegments: [],
  /** @type {{ chunks: Uint8Array[], text: string }[]} */
  turnTtsSegments: [],
  audioEl: null,

  thinkingBuf: "",
  lastThinkingFlush: 0,
  processLineText: "",

  /** @type {{id:string,role:'user'|'assistant',text:string,images?:string[]}[]} */
  messages: [],
  activeAssistantId: null,
  /** @type {{ id: string, url: string, name?: string, file?: File }[]} */
  pendingAttach: [],

  /** After barge-in / cancel, ignore late TTS until next turn. */
  dropRemoteTts: false,

  /** @type {ReturnType<typeof window.PixelBot.createPixelBot>[]} */
  bots: [],
};

export const LIMITS = {
  msg: 50,
  attach: 4,
  thinkingMinMs: 400,
  processMaxLen: 72,
};

/** Late-bound UI callbacks to avoid circular imports. */
export const hooks = {
  /** @type {(() => void) | null} */
  syncUi: null,
  /** @type {(() => void) | null} */
  replayLastTts: null,
  /** @type {(() => void) | null} */
  onMoodChanged: null,
};

export function runSyncUi() {
  if (hooks.syncUi) hooks.syncUi();
}

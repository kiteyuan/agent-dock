// Ambient globals for the desk-pet page (type-checked via desktop/tsconfig.json).

interface TauriGlobal {
  core: { invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T> };
  window: { getCurrentWindow(): any };
  [key: string]: any;
}

interface PixelBotApi {
  createPixelBot(...args: any[]): any;
  [key: string]: any;
}

interface Window {
  /** Injected by Tauri (`app.withGlobalTauri`); absent in a plain browser. */
  __TAURI__?: TauriGlobal;
  /** Classic script `pixel-bot.js`, loaded before the ES modules. */
  PixelBot: PixelBotApi;
  pixelBot?: any;
  webkitAudioContext?: typeof AudioContext;
}

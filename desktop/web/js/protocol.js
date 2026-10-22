/** Device Protocol envelope (align with runtime/protocol/device.py). */
export function encodeMsg(type, payload = {}) {
  return JSON.stringify({
    type,
    id: Math.random().toString(16).slice(2, 10),
    ts: Date.now() / 1000,
    payload,
  });
}

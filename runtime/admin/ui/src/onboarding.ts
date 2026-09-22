/** First-run Admin tour; bump suffix when steps change materially. */
export const ONBOARDING_STORAGE_KEY = "agentdock-admin-onboarding-v1";

export function isOnboardingDone(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_STORAGE_KEY) === "1";
  } catch {
    return true;
  }
}

export function markOnboardingDone() {
  try {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function resetOnboarding() {
  try {
    localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Prefer a visible target (mobile bottom nav vs desktop sider). */
export function tourEl(...selectors: string[]): HTMLElement | null {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el instanceof HTMLElement && el.offsetParent !== null) return el;
  }
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el instanceof HTMLElement) return el;
  }
  return null;
}

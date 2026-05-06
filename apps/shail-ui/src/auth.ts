/**
 * Auth helpers for the dashboard. Persists credentials in localStorage and
 * dispatches a 'shail-auth-updated' CustomEvent whenever credentials change
 * so the extension's dashboard-bridge content script can mirror them into
 * browser.storage.sync (keeps sidepanel + dashboard signed-in to the same
 * account on the same browser).
 */

const AUTH_EVENT = 'shail-auth-updated';

function notify() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_EVENT));
  }
}

export function getApiKey(): string | null {
  return localStorage.getItem('shail_api_key');
}

export function setApiKey(key: string, userId: string) {
  localStorage.setItem('shail_api_key', key);
  localStorage.setItem('shail_user_id', userId);
  notify();
}

export function clearAuth() {
  localStorage.removeItem('shail_api_key');
  localStorage.removeItem('shail_user_id');
  localStorage.removeItem('shail_email');
  localStorage.removeItem('shail_name');
  notify();
}

export function saveProfile(email: string, name: string) {
  localStorage.setItem('shail_email', email);
  localStorage.setItem('shail_name', name);
  notify();
}

export function getProfile(): { email: string; name: string } {
  return {
    email: localStorage.getItem('shail_email') ?? '',
    name:  localStorage.getItem('shail_name')  ?? '',
  };
}

/**
 * Hydrates auth from a `?token=...&user_id=...&email=...&name=...` URL
 * param if present, then strips the params from the address bar so they
 * don't linger in history. Called once at app boot in main.tsx.
 *
 * The sidepanel passes `?token=` when opening Basecamp so the dashboard
 * can authenticate without forcing a second sign-in.
 */
export function hydrateFromUrl(): boolean {
  if (typeof window === 'undefined') return false;
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token');
  if (!token) return false;

  localStorage.setItem('shail_api_key', token);
  const userId = url.searchParams.get('user_id');
  if (userId) localStorage.setItem('shail_user_id', userId);
  const email = url.searchParams.get('email');
  if (email) localStorage.setItem('shail_email', email);
  const name = url.searchParams.get('name');
  if (name) localStorage.setItem('shail_name', name);

  for (const k of ['token', 'user_id', 'email', 'name']) url.searchParams.delete(k);
  window.history.replaceState({}, '', url.toString());
  notify();
  return true;
}

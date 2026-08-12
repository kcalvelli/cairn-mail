/**
 * Bearer-token storage and wiring for the cairn-mail API.
 *
 * The API is single-user behind a shared token. We keep it in localStorage so
 * the installed PWA survives reloads without re-prompting, apply it to axios
 * (both the shared instance and the global default, since some call sites still
 * use raw axios) and to the WebSocket URL, and dispatch an event on 401 so the
 * app can show the token prompt.
 */

import axios from 'axios';

const TOKEN_KEY = 'cairn_mail_token';
export const AUTH_REQUIRED_EVENT = 'cairn-mail:auth-required';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** Store the token and apply it to axios defaults. */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  applyToken(token);
}

/** Forget the token and drop it from axios defaults. */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  applyToken(null);
}

/** Set or remove the Authorization header on the global axios default. */
export function applyToken(token: string | null): void {
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  } else {
    delete axios.defaults.headers.common['Authorization'];
  }
}

/** Fire the auth-required event so a listener can prompt for a token. */
export function notifyAuthRequired(): void {
  window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT));
}

/** Append the token to a WebSocket URL as a query parameter. */
export function withWsToken(url: string): string {
  const token = getToken();
  if (!token) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

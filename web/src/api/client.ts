export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { ...(init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
    const detailMessage = detail && typeof detail === 'object' && 'message' in detail ? detail.message : null;
    const message = typeof detail === 'string' ? detail : typeof detailMessage === 'string' ? detailMessage : detail ? JSON.stringify(detail) : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return body as T;
}

export function errorMessage(value: unknown): string {
  if (value instanceof Error) return value.message;
  if (typeof value === 'string') return value;
  return value ? JSON.stringify(value) : 'Something went wrong. Please try again.';
}

export function money(value: unknown, currency = 'USD'): string {
  const number = Number(value);
  return value == null || !Number.isFinite(number) ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(number);
}

export function number(value: unknown, digits = 0): string {
  const numeric = Number(value);
  return value == null || !Number.isFinite(numeric) ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(numeric);
}

export function timestamp(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

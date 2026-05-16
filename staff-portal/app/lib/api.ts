const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function headers(token: string) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

async function req<T>(
  token: string,
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers(token), ...(options?.headers ?? {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI validation errors return detail as an array of {msg, loc} objects.
    const detail = Array.isArray(err.detail)
      ? err.detail.map((e: { msg?: string }) => e.msg ?? "Validation error").join(", ")
      : err.detail ?? "Request failed";
    throw new Error(String(detail));
  }
  return res.json() as Promise<T>;
}

export const staffApi = {
  me: (token: string) => req(token, "/api/v1/staff/me"),

  listStaff: (token: string) => req<{ items: unknown[] }>(token, "/api/v1/staff/"),

  // Chat
  chat: (token: string, agent: string, message: string, thread_id?: string) =>
    req<{ reply: string; thread_id: string }>(token, "/api/v1/staff/chat", {
      method: "POST",
      body: JSON.stringify({ agent_name: agent, message, thread_id }),
    }),

  listThreads: (token: string) =>
    req<{ items: unknown[] }>(token, "/api/v1/staff/threads"),

  getThread: (token: string, threadId: string) =>
    req<{ messages: unknown[] }>(token, `/api/v1/staff/threads/${threadId}`),

  // Reminders
  listReminders: (token: string) =>
    req<{ items: unknown[] }>(token, "/api/v1/staff/reminders"),

  createReminder: (token: string, data: unknown) =>
    req(token, "/api/v1/staff/reminders", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  acknowledgeReminder: (token: string, reminderId: string) =>
    req(token, `/api/v1/staff/reminders/${reminderId}/acknowledge`, {
      method: "POST",
    }),

  snoozeReminder: (token: string, reminderId: string, hours: number) =>
    req(token, `/api/v1/staff/reminders/${reminderId}/snooze`, {
      method: "POST",
      body: JSON.stringify({ duration_hours: hours }),
    }),

  // Support
  listTickets: (token: string) =>
    req<{ items: unknown[] }>(token, "/api/v1/staff/support"),

  createTicket: (token: string, data: unknown) =>
    req(token, "/api/v1/staff/support", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// SWR fetcher factory
export function apiFetcher(token: string) {
  return (url: string) => req(token, url);
}

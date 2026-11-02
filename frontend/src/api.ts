export type User = { id: string; name: string; email: string };
export type LineItem = { name: string; quantity: string | null; unit_price: string | null; line_total: string | null };
export type Fields = {
  merchant: string | null;
  date: string | null;
  total: string | null;
  currency: string | null;
  tax: string | null;
  category: string;
  notes: string;
  items?: LineItem[];
};
export type Expense = {
  merchant: string;
  expenseDate: string;
  totalMinor: number;
  taxMinor: number | null;
  currency: string;
  currencyExponent: number;
  category: string;
  notes: string;
  items?: { name: string; quantity: string | null; unitPriceMinor: number | null; lineTotalMinor: number | null }[];
};
export type Receipt = {
  id: string;
  filename: string;
  page: number;
  status: string;
  revision: number;
  fields: Fields;
  prediction: Fields | null;
  warnings: string[];
  source: string;
  expense: Expense | null;
  createdAt: string;
};
export type Summary = {
  currencies: { _id: string; totalMinor: number; count: number }[];
  categories: {
    _id: { currency: string; category: string };
    totalMinor: number;
  }[];
  months: { _id: { currency: string; month: string }; totalMinor: number }[];
  pending: number;
};
export type Page = { items: Receipt[]; nextCursor: string | null };
export type AuthConfig = {
  googleClientId: string;
  devLogin: boolean;
  csrfToken: string;
};
export type Health = { extraction: string; maxUploadMb: number; maxPdfPages: number };
export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (options.method && options.method !== "GET" && !csrf) {
    const config = await api<AuthConfig>("/auth/config");
    setCsrf(config.csrfToken);
  }
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET")
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(
      response.status === 413
        ? "This file is too large. Choose a file within the displayed upload limit."
        : path === "/auth/config" && response.status === 404
        ? "The sign-in service is unavailable. Please try again later."
        : typeof error.detail === "string"
        ? error.detail
        : "Check the entered values and try again.",
    );
  }
  return response.json();
}

export async function uploadReceipt(file: File, maxUploadMb: number) {
  if (file.size > maxUploadMb * 1024 ** 2)
    throw new Error(`Choose a receipt no larger than ${maxUploadMb} MB.`);
  const data = new FormData();
  data.append("file", file);
  return api<{ receipts: Receipt[] }>("/receipts", { method: "POST", body: data });
}

export const exponents: Record<string, number> = {
  INR: 2,
  IDR: 2,
  MYR: 2,
  USD: 2,
  EUR: 2,
  GBP: 2,
  JPY: 0,
};
export function money(value: number, currency: string) {
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency,
    maximumFractionDigits: exponents[currency] ?? 2,
  }).format(value / 10 ** (exponents[currency] ?? 2));
}

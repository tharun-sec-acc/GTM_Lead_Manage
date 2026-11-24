/**
 * Unified API Configuration
 * Dynamically resolves the backend API URL based on browser location or environment variable.
 * Prevents IPv6 ::1 vs 127.0.0.1 mismatch and CORS errors.
 */

export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname || "127.0.0.1";
    const protocol = window.location.protocol || "http:";
    // Match the port 8000 on the same host the frontend is visited from
    return `${protocol}//${hostname}:8000`;
  }
  return process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";
}

export const API_BASE = getApiBase();
export const API = getApiBase();

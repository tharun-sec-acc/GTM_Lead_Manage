"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getApiBase } from "./api-config";

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_superadmin: boolean;
}

export interface OrganizationProfile {
  id: string;
  name: string;
  slug: string;
  domain?: string | null;
  plan: string;
  status: string;
  role?: string;
}

interface AuthContextType {
  user: UserProfile | null;
  organization: OrganizationProfile | null;
  organizations: OrganizationProfile[];
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; full_name: string; organization_name?: string; invitation_token?: string }) => Promise<void>;
  logout: () => Promise<void>;
  switchOrganization: (orgId: string) => Promise<void>;
  refreshUser: () => Promise<void>;
  fetchWithAuth: (url: string, init?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const getEndpoint = (path: string) => {
  const base = getApiBase();
  return path.startsWith("/") ? `${base}${path}` : `${base}/${path}`;
};

const PUBLIC_ROUTES = [
  "/",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [organization, setOrganization] = useState<OrganizationProfile | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationProfile[]>([]);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();
  const pathname = usePathname();

  const isPublicRoute = (path: string) => {
    if (PUBLIC_ROUTES.includes(path)) return true;
    if (path.startsWith("/invite/") || path.startsWith("/book/")) return true;
    return false;
  };

  const loadCurrentUser = async (jwtToken?: string | null) => {
    let activeToken = jwtToken !== undefined ? jwtToken : (typeof window !== "undefined" ? localStorage.getItem("gtm_access_token") : null);

    try {
      const headers: Record<string, string> = {};
      if (activeToken) {
        headers["Authorization"] = `Bearer ${activeToken}`;
      }

      // 1. Attempt /auth/me with Bearer token or HttpOnly cookie
      let res: Response;
      try {
        res = await fetch(getEndpoint("/auth/me"), {
          headers,
          credentials: "include",
        });
      } catch {
        // Offline or connection refused
        return;
      }

      // 2. If unauthorized, attempt cookie-based refresh token rotation
      if (res.status === 401) {
        try {
          const refreshRes = await fetch(getEndpoint("/auth/refresh"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
          });
          if (refreshRes.ok) {
            const refreshData = await refreshRes.json();
            activeToken = refreshData.access_token;
            if (activeToken && typeof window !== "undefined") {
              localStorage.setItem("gtm_access_token", activeToken);
            }
            res = await fetch(getEndpoint("/auth/me"), {
              headers: { Authorization: `Bearer ${activeToken}` },
              credentials: "include",
            });
          }
        } catch {
          // Refresh attempt failed
        }
      }

      if (res.ok) {
        const data = await res.json();
        setUser({
          id: data.id,
          email: data.email,
          full_name: data.full_name,
          avatar_url: data.avatar_url,
          is_active: data.is_active,
          is_verified: data.is_verified,
          is_superadmin: data.is_superadmin,
        });
        if (data.active_organization) {
          setOrganization(data.active_organization);
        }
        if (data.organizations) {
          setOrganizations(data.organizations);
        }
        setToken(activeToken);
        if (activeToken && typeof window !== "undefined") {
          localStorage.setItem("gtm_access_token", activeToken);
        }
      } else {
        // Token invalid or expired
        if (typeof window !== "undefined") {
          localStorage.removeItem("gtm_access_token");
        }
        setUser(null);
        setOrganization(null);
        setOrganizations([]);
        setToken(null);
      }
    } catch {
      // Offline or network error
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCurrentUser();
  }, []);

  useEffect(() => {
    if (!isLoading && !user && !isPublicRoute(pathname)) {
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [isLoading, user, pathname]);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      let res: Response;
      try {
        res = await fetch(getEndpoint("/auth/login"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
          credentials: "include",
        });
      } catch (networkErr: any) {
        throw new Error(`Unable to connect to backend at ${getApiBase()}. Please ensure the API is running.`);
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Login failed" }));
        throw new Error(err.detail || "Invalid email or password");
      }

      const data = await res.json();
      if (typeof window !== "undefined") {
        localStorage.setItem("gtm_access_token", data.access_token);
      }
      setToken(data.access_token);
      await loadCurrentUser(data.access_token);
      router.push("/dashboard");
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data: { email: string; password: string; full_name: string; organization_name?: string; invitation_token?: string }) => {
    setIsLoading(true);
    try {
      let res: Response;
      try {
        res = await fetch(getEndpoint("/auth/register"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
          credentials: "include",
        });
      } catch (networkErr: any) {
        throw new Error(`Unable to connect to backend at ${getApiBase()}. Please ensure the API is running.`);
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Registration failed" }));
        throw new Error(err.detail || "Registration failed");
      }

      const resData = await res.json();
      if (typeof window !== "undefined") {
        localStorage.setItem("gtm_access_token", resData.access_token);
      }
      setToken(resData.access_token);
      await loadCurrentUser(resData.access_token);
      router.push("/dashboard");
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await fetch(getEndpoint("/auth/logout"), {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // quiet catch
    } finally {
      if (typeof window !== "undefined") {
        localStorage.removeItem("gtm_access_token");
      }
      setUser(null);
      setOrganization(null);
      setOrganizations([]);
      setToken(null);
      setIsLoading(false);
      router.push("/login");
    }
  };

  const switchOrganization = async (orgId: string) => {
    if (!token) return;
    setIsLoading(true);
    try {
      const res = await fetch(getEndpoint(`/auth/switch-org/${orgId}`), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        if (typeof window !== "undefined") {
          localStorage.setItem("gtm_access_token", data.access_token);
        }
        setToken(data.access_token);
        await loadCurrentUser(data.access_token);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const refreshUser = async () => {
    await loadCurrentUser();
  };

  const fetchWithAuth = async (url: string, init?: RequestInit): Promise<Response> => {
    const headers = new Headers(init?.headers || {});
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (organization?.id) {
      headers.set("X-Organization-Id", organization.id);
    }
    const targetUrl = url.startsWith("http") ? url : getEndpoint(url);
    return fetch(targetUrl, {
      ...init,
      headers,
      credentials: "include",
    });
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        organizations,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        switchOrganization,
        refreshUser,
        fetchWithAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

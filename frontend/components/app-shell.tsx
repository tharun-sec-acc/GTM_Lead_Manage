"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import UiIcon, { type IconName } from "./ui-icon";
import ProductSelector from "./product-selector";
import { useAuth } from "../lib/auth-context";
import { getApiBase } from "../lib/api-config";

const mainNavigation: { href: string; label: string; icon: IconName; description: string }[] = [
  { href: "/overview", label: "Global overview", icon: "grid", description: "Consolidated performance across products" },
  { href: "/dashboard", label: "Dashboard", icon: "companies", description: "Import, research and outreach" },
  { href: "/#companies", label: "Companies & leads", icon: "companies", description: "Import, discover and connect" },
  { href: "/crm", label: "Sales pipeline", icon: "spark", description: "Opportunities, tasks and forecast" },
  { href: "/advertising", label: "Advertising", icon: "spark", description: "Ad campaigns, forms and lead attribution" },
  { href: "/intelligence", label: "Company intelligence", icon: "spark", description: "Evidence-backed company research" },
  { href: "/market-intelligence", label: "Market Intelligence", icon: "search", description: "Automotive discoveries & opportunity detection" },
  { href: "/followups", label: "Outreach", icon: "mail", description: "Thoughtful outreach, reviewed by you" },
  { href: "/meetings", label: "Calendar", icon: "calendar", description: "Organizer availability & AI MoM" },
  { href: "/zoho", label: "Zoho CRM", icon: "link", description: "Zoho CRM synchronization" },
];

const settingsNavigation: { href: string; label: string; icon: IconName; description: string }[] = [
  { href: "/settings/email-accounts", label: "Email Accounts", icon: "mail", description: "Connect Gmail & Outlook sending" },
  { href: "/settings/integrations", label: "Integrations Hub", icon: "link", description: "Google, MS 365, Zoho & Apollo OAuth" },
  { href: "/settings/team", label: "Team & Roles", icon: "companies", description: "Member invitations and permissions" },
  { href: "/settings/billing", label: "Billing & Plan", icon: "grid", description: "Subscription, entitlements and usage" },
  { href: "/settings/organization", label: "Organization", icon: "grid", description: "Tenant profile and plans" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, organization, organizations, logout, switchOrganization, isAuthenticated } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [orgDropdownOpen, setOrgDropdownOpen] = useState(false);
  const [unreadAlertsCount, setUnreadAlertsCount] = useState<number>(0);

  const isPublicPage =
    pathname === "/" ||
    pathname === "/login" ||
    pathname === "/register" ||
    pathname === "/forgot-password" ||
    pathname === "/reset-password" ||
    pathname.startsWith("/invite/") ||
    pathname.startsWith("/book/");

  useEffect(() => {
    if (isPublicPage) return;
    const fetchUnread = async () => {
      try {
        const apiUrl = getApiBase();
        const res = await fetch(`${apiUrl}/api/market-intelligence/alerts?unread_only=true`, { cache: "no-store" });
        if (res.ok) {
          const alerts = await res.json();
          setUnreadAlertsCount(alerts.length);
        }
      } catch {
        // quiet ignore in local/offline
      }
    };
    fetchUnread();
    const interval = setInterval(fetchUnread, 15000);
    return () => clearInterval(interval);
  }, [pathname, isPublicPage]);

  // For public marketing, standalone auth or booking pages, render content directly
  if (isPublicPage) {
    return <div id="workspace-content">{children}</div>;
  }

  const allNav = [...mainNavigation, ...settingsNavigation];
  const current = allNav.find(item =>
    item.href === "/dashboard" ? pathname === "/" || pathname === "/dashboard"
    : item.href === "/#companies" ? pathname.startsWith("/leads/")
    : pathname === item.href || pathname.startsWith(`${item.href}/`)
  );

  return (
    <div className={`app-shell${menuOpen ? " menu-open" : ""}`} onKeyDown={event => {
      if (event.key === "Escape") setMenuOpen(false);
    }}>
      <a className="skip-link" href="#workspace-content">Skip to content</a>
      <aside className="sidebar" id="workspace-sidebar">
        <Link href="/dashboard" className="brand" onClick={() => setMenuOpen(false)} aria-label="Solwer GTM Intelligence">
          <div className="brand-emblem">
            <svg width="34" height="34" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="34" height="34" rx="9" fill="#0f172a" />
              <path d="M17 6L26.5 11.5V22.5L17 28L7.5 22.5V11.5L17 6Z" stroke="url(#brandGradient)" strokeWidth="2.2" strokeLinejoin="round" fill="rgba(99, 102, 241, 0.12)" />
              <path d="M17 6V17M17 17L26.5 22.5M17 17L7.5 22.5" stroke="url(#brandGradient)" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="17" cy="17" r="2.8" fill="#e11d48" />
              <defs>
                <linearGradient id="brandGradient" x1="7.5" y1="6" x2="26.5" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#6366f1" />
                  <stop offset="0.5" stopColor="#a855f7" />
                  <stop offset="1" stopColor="#e11d48" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div className="brand-info">
            <div className="brand-title-row">
              <span className="brand-title">SOLWER</span>
              <span className="brand-badge-tag">GTM</span>
            </div>
            <span className="brand-subtitle">Sales Intelligence Engine</span>
          </div>
        </Link>

        {/* Organization Switcher */}
        {organization && (
          <div style={{ padding: "0 16px 12px 16px", position: "relative" }}>
            <button
              onClick={() => setOrgDropdownOpen(!orgDropdownOpen)}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                borderRadius: 8,
                color: "#ffffff",
                fontSize: 13,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                🏢 {organization.name}
              </span>
              <span style={{ fontSize: 10, opacity: 0.7 }}>▼</span>
            </button>
            {orgDropdownOpen && organizations.length > 0 && (
              <div style={{
                position: "absolute",
                top: "100%",
                left: 16,
                right: 16,
                background: "#1e293b",
                border: "1px solid #334155",
                borderRadius: 8,
                boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.3)",
                zIndex: 100,
                overflow: "hidden",
                marginTop: 4,
              }}>
                <div style={{ padding: "6px 10px", fontSize: 11, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>
                  Organizations
                </div>
                {organizations.map((org) => (
                  <button
                    key={org.id}
                    onClick={() => {
                      switchOrganization(org.id);
                      setOrgDropdownOpen(false);
                    }}
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      background: org.id === organization.id ? "rgba(99, 102, 241, 0.2)" : "transparent",
                      border: "none",
                      color: "#ffffff",
                      fontSize: 13,
                      textAlign: "left",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <span>{org.name}</span>
                    {org.id === organization.id && <span style={{ color: "#6366f1" }}>✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <p className="nav-caption">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {mainNavigation.map(item => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={current?.href === item.href ? "page" : undefined}
              className={`nav-link${current?.href === item.href ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              <UiIcon name={item.icon} />
              <span>{item.label}</span>
              {item.icon === "spark" && <span className="nav-tag">AI</span>}
              {item.href === "/market-intelligence" && unreadAlertsCount > 0 && (
                <span
                  style={{
                    marginLeft: "auto",
                    background: "var(--red, #e11d48)",
                    color: "#ffffff",
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "1px 6px",
                    borderRadius: 999,
                    display: "inline-flex",
                    alignItems: "center",
                    lineHeight: "14px",
                  }}
                >
                  {unreadAlertsCount}
                </span>
              )}
            </Link>
          ))}
        </nav>

        <p className="nav-caption" style={{ marginTop: 16 }}>ADMINISTRATION</p>
        <nav aria-label="Settings navigation">
          {settingsNavigation.map(item => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={current?.href === item.href ? "page" : undefined}
              className={`nav-link${current?.href === item.href ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              <UiIcon name={item.icon} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-guide">
          <span className="icon-tile"><UiIcon name="link" /></span>
          <strong>Evidence before outreach.</strong>
          <p>Research the company. Review the sources. Make every conversation relevant.</p>
          <Link href="/intelligence" onClick={() => setMenuOpen(false)}>
            Explore intelligence <UiIcon name="arrow" size={16} />
          </Link>
        </div>

        {/* User Card at Sidebar Bottom */}
        <div className="sidebar-bottom">
          <span className="local-dot" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <strong>{user ? user.full_name : "Demo User"}</strong>
            <small style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
              {user ? user.email : "Local workspace"}
            </small>
          </div>
          {user ? (
            <button
              onClick={() => logout()}
              title="Sign out"
              style={{
                background: "transparent",
                border: "none",
                color: "#94a3b8",
                cursor: "pointer",
                padding: 4,
                fontSize: 13,
              }}
            >
              Sign out
            </button>
          ) : (
            <Link
              href="/login"
              style={{
                fontSize: 12,
                color: "#6366f1",
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              Sign in
            </Link>
          )}
        </div>
      </aside>

      <div className="app-content">
        <div className="workspace-topbar">
          <div className="topbar-title">
            <button
              className="icon-button mobile-menu"
              aria-label="Toggle navigation"
              aria-expanded={menuOpen}
              aria-controls="workspace-sidebar"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              <UiIcon name="menu" />
            </button>
            <span className="topbar-org">{organization ? organization.name : "Solwer GTM"}</span>
            <span className="breadcrumb-divider">/</span>
            <strong className="topbar-view-title">{current?.label || "Workspace"}</strong>
          </div>
          <ProductSelector />
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Link
              href="/settings/profile"
              style={{
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                background: "#f1f5f9",
                padding: "6px 12px",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                color: "#1e293b",
              }}
            >
              <span>👤 {user ? user.full_name : "Account"}</span>
            </Link>
            <span className="workspace-label">
              <span className="local-dot-pulse" />
              <span>{organization?.plan?.toUpperCase() || "ENTERPRISE"} SAAS</span>
            </span>
          </div>
        </div>
        <div id="workspace-content" tabIndex={-1}>{children}</div>
      </div>
    </div>
  );
}

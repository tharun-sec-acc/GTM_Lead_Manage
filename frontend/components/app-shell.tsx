"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import UiIcon, { type IconName } from "./ui-icon";
import ProductSelector from "./product-selector";

const navigation: { href: string; label: string; icon: IconName; description: string }[] = [
  { href: "/overview", label: "Global overview", icon: "grid", description: "Consolidated performance across products" },
  { href: "/dashboard", label: "Dashboard", icon: "companies", description: "Import, research and outreach" },
  { href: "/#companies", label: "Companies & leads", icon: "companies", description: "Import, discover and connect" },
  { href: "/intelligence", label: "Company intelligence", icon: "spark", description: "Evidence-backed company research" },
  { href: "/market-intelligence", label: "Market Intelligence", icon: "search", description: "Automotive discoveries & opportunity detection" },
  { href: "/followups", label: "Outreach", icon: "mail", description: "Thoughtful outreach, reviewed by you" },
  { href: "/meetings", label: "Calendar", icon: "calendar", description: "Organizer availability & AI MoM" },
  { href: "/zoho", label: "Zoho CRM", icon: "link", description: "Zoho CRM synchronization" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unreadAlertsCount, setUnreadAlertsCount] = useState<number>(0);

  useEffect(() => {
    const fetchUnread = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
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
  }, [pathname]);

  const current = navigation.find(item => item.href === "/dashboard" ? pathname === "/" || pathname === "/dashboard"
    : item.href === "/#companies" ? pathname.startsWith("/leads/")
    : pathname === item.href || pathname.startsWith(`${item.href}/`));
  return <div className={`app-shell${menuOpen ? " menu-open" : ""}`} onKeyDown={event => {
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
      <p className="nav-caption">WORKSPACE</p>
      <nav aria-label="Main navigation">
        {navigation.map(item => <Link key={item.href} href={item.href}
          aria-current={current?.href === item.href ? "page" : undefined}
          className={`nav-link${current?.href === item.href ? " active" : ""}`}
          onClick={() => setMenuOpen(false)}><UiIcon name={item.icon} /><span>{item.label}</span>
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
        </Link>)}
      </nav>
      <div className="sidebar-guide">
        <span className="icon-tile"><UiIcon name="link" /></span>
        <strong>Evidence before outreach.</strong>
        <p>Research the company. Review the sources. Make every conversation relevant.</p>
        <Link href="/intelligence" onClick={() => setMenuOpen(false)}>Explore intelligence <UiIcon name="arrow" size={16} /></Link>
      </div>
      <div className="sidebar-bottom"><span className="local-dot" /><div><strong>Local workspace</strong><small>Private pilot · No sign-in</small></div></div>
    </aside>
    <div className="app-content">
      <div className="workspace-topbar">
        <div className="topbar-title">
          <button className="icon-button mobile-menu" aria-label="Toggle navigation"
            aria-expanded={menuOpen} aria-controls="workspace-sidebar" onClick={() => setMenuOpen(!menuOpen)}>
            <UiIcon name="menu" />
          </button>
          <span className="topbar-org">Solwer GTM</span>
          <span className="breadcrumb-divider">/</span>
          <strong className="topbar-view-title">{current?.label || "Workspace"}</strong>
        </div>
        <ProductSelector />
        <span className="workspace-label">
          <span className="local-dot-pulse" />
          <span>PRODUCTION PILOT</span>
        </span>
      </div>
      <div id="workspace-content" tabIndex={-1}>{children}</div>
    </div>
  </div>;
}

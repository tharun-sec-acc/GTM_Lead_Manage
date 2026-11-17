"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import UiIcon, { type IconName } from "./ui-icon";
import ProductSelector from "./product-selector";

const navigation: { href: string; label: string; icon: IconName; description: string }[] = [
  { href: "/overview", label: "Global overview", icon: "grid", description: "Consolidated performance across products" },
  { href: "/dashboard", label: "Dashboard", icon: "companies", description: "Import, research and outreach" },
  { href: "/#companies", label: "Companies & leads", icon: "companies", description: "Import, discover and connect" },
  { href: "/intelligence", label: "Company intelligence", icon: "spark", description: "Evidence-backed company research" },
  { href: "/followups", label: "Outreach", icon: "mail", description: "Thoughtful outreach, reviewed by you" },
  { href: "/meetings", label: "Calendar", icon: "calendar", description: "Organizer availability" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const current = navigation.find(item => item.href === "/dashboard" ? pathname === "/" || pathname === "/dashboard"
    : item.href === "/#companies" ? pathname.startsWith("/leads/")
    : pathname === item.href || pathname.startsWith(`${item.href}/`));
  return <div className={`app-shell${menuOpen ? " menu-open" : ""}`} onKeyDown={event => {
    if (event.key === "Escape") setMenuOpen(false);
  }}>
    <a className="skip-link" href="#workspace-content">Skip to content</a>
    <aside className="sidebar" id="workspace-sidebar">
      <Link href="/dashboard" className="brand" onClick={() => setMenuOpen(false)} aria-label="DENSO Prospecting overview">
        <span className="brand-mark">DENSO</span><span className="brand-product">GTM Prospecting<span>SALES INTELLIGENCE WORKSPACE</span></span>
      </Link>
      <p className="nav-caption">WORKSPACE</p>
      <nav aria-label="Main navigation">
        {navigation.map(item => <Link key={item.href} href={item.href}
          aria-current={current?.href === item.href ? "page" : undefined}
          className={`nav-link${current?.href === item.href ? " active" : ""}`}
          onClick={() => setMenuOpen(false)}><UiIcon name={item.icon} /><span>{item.label}</span>
          {item.icon === "spark" && <span className="nav-tag">AI</span>}
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
        <div className="topbar-title"><button className="icon-button mobile-menu" aria-label="Toggle navigation"
          aria-expanded={menuOpen} aria-controls="workspace-sidebar" onClick={() => setMenuOpen(!menuOpen)}><UiIcon name="menu" /></button>
          <span>DENSO</span><span className="breadcrumb-divider">/</span><strong>{current?.label || "Workspace"}</strong>
        </div>
        <ProductSelector />
        <span className="workspace-label"><span className="local-dot" /> LOCAL PILOT</span>
      </div>
      <div id="workspace-content" tabIndex={-1}>{children}</div>
    </div>
  </div>;
}

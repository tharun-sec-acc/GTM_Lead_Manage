"use client";

import Link from "next/link";
import { useAuth } from "../lib/auth-context";

export default function SaaSMarketingHomePage() {
  const { user, organization, isAuthenticated, isLoading } = useAuth();

  return (
    <div className="landing-page" style={{ minHeight: "100vh", backgroundColor: "#0b0f17", color: "#f8fafc", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {/* 1. Global Navigation Bar */}
      <header style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        backgroundColor: "rgba(11, 15, 23, 0.85)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
        padding: "16px 24px",
      }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "38px",
              height: "38px",
              borderRadius: "10px",
              background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 20px rgba(99, 102, 241, 0.35)",
            }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: "1.2rem", fontWeight: "800", letterSpacing: "-0.02em", color: "#ffffff", display: "flex", alignItems: "center", gap: "6px" }}>
                SOLWER <span style={{ fontSize: "0.75rem", padding: "2px 6px", borderRadius: "4px", background: "rgba(99, 102, 241, 0.2)", color: "#818cf8", border: "1px solid rgba(99, 102, 241, 0.4)" }}>GTM</span>
              </div>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Sales Intelligence Platform</div>
            </div>
          </div>

          <nav style={{ display: "flex", alignItems: "center", gap: "28px" }}>
            <a href="#features" style={{ color: "#94a3b8", textDecoration: "none", fontSize: "0.95rem", fontWeight: "500", transition: "color 0.2s" }}>Features</a>
            <a href="#outreach" style={{ color: "#94a3b8", textDecoration: "none", fontSize: "0.95rem", fontWeight: "500", transition: "color 0.2s" }}>Outreach & Email</a>
            <a href="#meetings" style={{ color: "#94a3b8", textDecoration: "none", fontSize: "0.95rem", fontWeight: "500", transition: "color 0.2s" }}>Meetings Copilot</a>
            <a href="#about" style={{ color: "#94a3b8", textDecoration: "none", fontSize: "0.95rem", fontWeight: "500", transition: "color 0.2s" }}>About</a>
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            {!isLoading && isAuthenticated && user ? (
              <Link
                href="/dashboard"
                style={{
                  padding: "10px 20px",
                  borderRadius: "8px",
                  background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
                  color: "#ffffff",
                  textDecoration: "none",
                  fontWeight: "600",
                  fontSize: "0.95rem",
                  boxShadow: "0 4px 14px rgba(79, 70, 229, 0.4)",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <span>Dashboard ({organization?.name || "Workspace"})</span>
                <span>&rarr;</span>
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  style={{
                    color: "#e2e8f0",
                    textDecoration: "none",
                    fontSize: "0.95rem",
                    fontWeight: "600",
                    padding: "8px 16px",
                    borderRadius: "6px",
                    transition: "background 0.2s",
                  }}
                >
                  Sign In
                </Link>
                <Link
                  href="/register"
                  style={{
                    padding: "9px 20px",
                    borderRadius: "8px",
                    background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
                    color: "#ffffff",
                    textDecoration: "none",
                    fontWeight: "600",
                    fontSize: "0.95rem",
                    boxShadow: "0 4px 16px rgba(99, 102, 241, 0.35)",
                  }}
                >
                  Get Started Free
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* 2. Hero Section */}
      <section style={{ padding: "80px 24px 60px", maxWidth: "1100px", margin: "0 auto", textAlign: "center" }}>
        <div style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 14px",
          borderRadius: "9999px",
          background: "rgba(99, 102, 241, 0.12)",
          border: "1px solid rgba(99, 102, 241, 0.3)",
          color: "#a5b4fc",
          fontSize: "0.85rem",
          fontWeight: "600",
          marginBottom: "24px",
        }}>
          <span style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#10b981" }} />
          Multi-Tenant Sales Intelligence & Direct Outreach SaaS
        </div>

        <h1 style={{
          fontSize: "clamp(2.5rem, 5vw, 4rem)",
          fontWeight: "800",
          lineHeight: "1.15",
          letterSpacing: "-0.03em",
          marginBottom: "24px",
          background: "linear-gradient(180deg, #ffffff 0%, #cbd5e1 100%)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
        }}>
          Supercharge Your GTM Pipeline With Evidence-Grounded Intelligence
        </h1>

        <p style={{
          fontSize: "1.25rem",
          lineHeight: "1.6",
          color: "#94a3b8",
          maxWidth: "760px",
          margin: "0 auto 40px",
        }}>
          From automated lead discovery and deep executive intelligence to native email outreach through your own Gmail &amp; Outlook accounts. All in one multi-tenant workspace.
        </p>

        <div style={{ display: "flex", justifyContent: "center", gap: "16px", flexWrap: "wrap" }}>
          <Link
            href="/register"
            style={{
              padding: "14px 32px",
              borderRadius: "10px",
              background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
              color: "#ffffff",
              textDecoration: "none",
              fontWeight: "700",
              fontSize: "1.05rem",
              boxShadow: "0 6px 20px rgba(79, 70, 229, 0.45)",
            }}
          >
            Start Free 14-Day Trial &rarr;
          </Link>
          <Link
            href="/login"
            style={{
              padding: "14px 28px",
              borderRadius: "10px",
              backgroundColor: "rgba(255, 255, 255, 0.05)",
              color: "#f1f5f9",
              border: "1px solid rgba(255, 255, 255, 0.15)",
              textDecoration: "none",
              fontWeight: "600",
              fontSize: "1.05rem",
            }}
          >
            Access Organization
          </Link>
        </div>
      </section>

      {/* 3. Key Feature Pillars */}
      <section id="features" style={{ padding: "60px 24px", maxWidth: "1200px", margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: "50px" }}>
          <h2 style={{ fontSize: "2.2rem", fontWeight: "700", color: "#f8fafc", marginBottom: "12px" }}>
            Engineered for Modern Enterprise Sales Teams
          </h2>
          <p style={{ color: "#94a3b8", fontSize: "1.1rem" }}>Everything you need to find, research, reach, and close high-value accounts.</p>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "24px",
        }}>
          {/* Card 1 */}
          <div style={{
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "32px",
          }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: "rgba(99, 102, 241, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.3rem", fontWeight: "700", marginBottom: "10px", color: "#ffffff" }}>User-Owned OAuth Outreach</h3>
            <p style={{ color: "#94a3b8", lineHeight: "1.6", fontSize: "0.95rem" }}>
              Connect your authorized Google Workspace or Microsoft 365 Outlook accounts. Send personalized outreach emails that land in customer inboxes and sync to your own Sent folder.
            </p>
          </div>

          {/* Card 2 */}
          <div style={{
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "32px",
          }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: "rgba(16, 185, 129, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.3rem", fontWeight: "700", marginBottom: "10px", color: "#ffffff" }}>Unified Meeting Copilot</h3>
            <p style={{ color: "#94a3b8", lineHeight: "1.6", fontSize: "0.95rem" }}>
              Support for both Microsoft Teams and Google Meet. Automatically check organizer calendar availability, generate booking links, and produce AI meeting minutes.
            </p>
          </div>

          {/* Card 3 */}
          <div style={{
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "32px",
          }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: "rgba(244, 63, 94, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fb7185" strokeWidth="2">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.3rem", fontWeight: "700", marginBottom: "10px", color: "#ffffff" }}>Apollo &amp; Deep Intelligence</h3>
            <p style={{ color: "#94a3b8", lineHeight: "1.6", fontSize: "0.95rem" }}>
              Enrich prospective companies with verified decision-maker contacts from Apollo.io and autonomous public crawler agents powered by AWS Bedrock AI.
            </p>
          </div>

          {/* Card 4 */}
          <div style={{
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "32px",
          }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: "rgba(234, 179, 8, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#facc15" strokeWidth="2">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.3rem", fontWeight: "700", marginBottom: "10px", color: "#ffffff" }}>Multi-Sheet Excel Lead Imports</h3>
            <p style={{ color: "#94a3b8", lineHeight: "1.6", fontSize: "0.95rem" }}>
              Upload massive lead lists with intelligent column mapping, deduplication across company keys, and instant organization-scoped data isolation.
            </p>
          </div>

          {/* Card 5 */}
          <div style={{
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "32px",
          }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: "rgba(168, 85, 247, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#c084fc" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.3rem", fontWeight: "700", marginBottom: "10px", color: "#ffffff" }}>Enterprise RBAC &amp; Tenant Security</h3>
            <p style={{ color: "#94a3b8", lineHeight: "1.6", fontSize: "0.95rem" }}>
              Invite sales reps, managers, and admins with strict role-based access control. Every record is protected with row-level organization boundaries.
            </p>
          </div>

          {/* Card 6 */}
          <div style={{
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "32px",
          }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: "rgba(59, 130, 246, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.3rem", fontWeight: "700", marginBottom: "10px", color: "#ffffff" }}>Zoho CRM Bidirectional Sync</h3>
            <p style={{ color: "#94a3b8", lineHeight: "1.6", fontSize: "0.95rem" }}>
              Seamlessly sync qualified leads, contacts, and deal stages with Zoho CRM using the modern v8 REST API and webhook-driven updates.
            </p>
          </div>
        </div>
      </section>

      {/* 4. CTA Banner */}
      <section style={{ padding: "80px 24px", maxWidth: "1000px", margin: "40px auto", textAlign: "center", backgroundColor: "rgba(99, 102, 241, 0.08)", borderRadius: "24px", border: "1px solid rgba(99, 102, 241, 0.2)" }}>
        <h2 style={{ fontSize: "2.2rem", fontWeight: "800", color: "#ffffff", marginBottom: "16px" }}>
          Ready to scale your sales prospecting?
        </h2>
        <p style={{ color: "#cbd5e1", fontSize: "1.1rem", maxWidth: "600px", margin: "0 auto 32px" }}>
          Join high-growth sales teams utilizing Solwer GTM to identify, research, and engage key accounts.
        </p>
        <Link
          href="/register"
          style={{
            display: "inline-block",
            padding: "14px 36px",
            borderRadius: "10px",
            background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
            color: "#ffffff",
            textDecoration: "none",
            fontWeight: "700",
            fontSize: "1.1rem",
            boxShadow: "0 6px 24px rgba(99, 102, 241, 0.4)",
          }}
        >
          Create Your Organization &rarr;
        </Link>
      </section>

      {/* 5. Footer */}
      <footer id="about" style={{
        borderTop: "1px solid rgba(255, 255, 255, 0.08)",
        padding: "48px 24px 36px",
        maxWidth: "1200px",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: "24px",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: "28px", height: "28px", borderRadius: "6px", background: "#4f46e5", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
            <span style={{ fontWeight: "700", color: "#ffffff" }}>SOLWER GTM Platform</span>
          </div>
          <div style={{ display: "flex", gap: "24px", fontSize: "0.9rem", color: "#64748b" }}>
            <Link href="/login" style={{ color: "#94a3b8", textDecoration: "none" }}>Sign In</Link>
            <Link href="/register" style={{ color: "#94a3b8", textDecoration: "none" }}>Register</Link>
            <Link href="/settings/integrations" style={{ color: "#94a3b8", textDecoration: "none" }}>Integrations</Link>
          </div>
        </div>
        <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "20px", display: "flex", justifyContent: "space-between", fontSize: "0.85rem", color: "#64748b" }}>
          <span>&copy; {new Date().getFullYear()} Solwer GTM Sales Intelligence. All rights reserved.</span>
          <span>Enterprise Multi-Tenant SaaS</span>
        </div>
      </footer>
    </div>
  );
}

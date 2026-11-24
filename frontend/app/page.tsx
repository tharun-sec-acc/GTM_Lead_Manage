"use client";

import Link from "next/link";
import { useAuth } from "../lib/auth-context";

const features = [
  {
    title: "User-owned OAuth outreach",
    body:
      "Connect authorized Google Workspace or Microsoft 365 accounts. Send personalized outreach from your own mailbox and keep replies in one reviewable inbox.",
    icon: "mail",
    tone: "rose",
  },
  {
    title: "Unified meeting copilot",
    body:
      "Run Microsoft Teams and Google Meet from one calendar. Check organizer availability, publish booking links and generate AI minutes with action items.",
    icon: "clock",
    tone: "emerald",
  },
  {
    title: "Apollo & deep intelligence",
    body:
      "Enrich companies with decision-makers from Apollo, then verify claims with cited research from public crawlers and AWS Bedrock extraction.",
    icon: "spark",
    tone: "amber",
  },
  {
    title: "Multi-sheet Excel imports",
    body:
      "Map each worksheet independently, import in the background and review row-level reports with duplicate detection and import provenance.",
    icon: "layers",
    tone: "sky",
  },
  {
    title: "Roles & tenant boundaries",
    body:
      "Invite reps, managers and admins with role-based access. Every lead, campaign and booking is scoped to its organization.",
    icon: "shield",
    tone: "violet",
  },
  {
    title: "Zoho CRM sync",
    body:
      "Keep leads, contacts and deal stages aligned through editable field mappings, conflict policies and scheduled inbound/outbound sync jobs.",
    icon: "sync",
    tone: "blue",
  },
] as const;

const stack = [
  "Google Workspace",
  "Microsoft 365",
  "Zoho CRM",
  "AWS Bedrock",
  "Apollo",
  "PostgreSQL",
];

const flow = [
  {
    title: "Import and qualify",
    body: "Bring in spreadsheets, confirm the official domain and keep duplicate candidates visible for review.",
  },
  {
    title: "Research with evidence",
    body: "Collect cited company facts, financial qualifiers and leadership signals — every claim keeps its source.",
  },
  {
    title: "Reach and close",
    body: "Approve drafts, book the meeting, review AI minutes and push the qualified deal into Zoho CRM.",
  },
];

function Icon({ name }: { name: string }) {
  const common = {
    width: 21,
    height: 21,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (name) {
    case "mail":
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="14" rx="2.5" />
          <path d="m3.5 7 8.5 6 8.5-6" />
        </svg>
      );
    case "clock":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7.5V12l3.2 1.9" />
        </svg>
      );
    case "spark":
      return (
        <svg {...common}>
          <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z" />
          <path d="M18.5 14.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9.9-2.1Z" />
        </svg>
      );
    case "layers":
      return (
        <svg {...common}>
          <path d="m12 3 8.5 4.7L12 12.4 3.5 7.7 12 3Z" />
          <path d="m3.5 12 8.5 4.7 8.5-4.7" />
          <path d="m3.5 16.3 8.5 4.7 8.5-4.7" />
        </svg>
      );
    case "shield":
      return (
        <svg {...common}>
          <path d="M12 3.2 5 6v5.4c0 4.2 2.9 7.6 7 9.4 4.1-1.8 7-5.2 7-9.4V6l-7-2.8Z" />
          <path d="m9.2 12.1 2 2 3.6-3.9" />
        </svg>
      );
    case "sync":
      return (
        <svg {...common}>
          <path d="M20 11a8 8 0 0 0-13.7-4.6L3.5 9" />
          <path d="M3.5 4.5V9H8" />
          <path d="M4 13a8 8 0 0 0 13.7 4.6l2.8-2.6" />
          <path d="M20.5 19.5V15H16" />
        </svg>
      );
    default:
      return null;
  }
}

function Check() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m4 12.5 5 5L20 6.5" />
    </svg>
  );
}

export default function SaaSMarketingHomePage() {
  const { user, organization, isAuthenticated, isLoading } = useAuth();
  const signedIn = !isLoading && isAuthenticated && user;

  return (
    <div className="landing">
      <header className="site-header">
        <div className="site-header-inner">
          <Link href="/" className="site-brand" aria-label="Solwer GTM home">
            <span className="site-brand-mark">
              <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2.6 2.8 7.3 12 12l9.2-4.7L12 2.6Z" />
                <path d="m2.8 16.7 9.2 4.7 9.2-4.7" />
                <path d="m2.8 12 9.2 4.7 9.2-4.7" />
              </svg>
            </span>
            <span>
              <span className="site-brand-name">
                SOLWER
                <span className="site-brand-tag">GTM</span>
              </span>
              <span className="site-brand-sub">Sales Intelligence Platform</span>
            </span>
          </Link>

          <nav className="site-links" aria-label="Marketing navigation">
            <a href="#features">Features</a>
            <a href="#outreach">Outreach &amp; Email</a>
            <a href="#meetings">Meetings Copilot</a>
            <a href="#about">About</a>
          </nav>

          <div className="site-actions">
            {signedIn ? (
              <Link href="/dashboard" className="btn-cta">
                Open dashboard <span aria-hidden="true">→</span>
              </Link>
            ) : (
              <>
                <Link href="/login" className="btn-ghost">
                  Sign in
                </Link>
                <Link href="/register" className="btn-cta">
                  Get started free
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <section className="hero">
        <div>
          <span className="hero-eyebrow">
            <span className="dot" /> Multi-tenant sales intelligence &amp; outreach
          </span>
          <h1 className="hero-title">
            Turn market signals into <span className="grad">qualified conversations</span>
          </h1>
          <p className="hero-sub">
            Solwer GTM connects lead import, cited company research, market intelligence, human-approved email
            and meeting follow-through in one workspace — so every conversation starts with evidence.
          </p>
          <div className="hero-ctas">
            <Link href={signedIn ? "/dashboard" : "/register"} className="btn-cta large">
              {signedIn ? `Open ${organization?.name || "workspace"}` : "Create your workspace"} <span aria-hidden="true">→</span>
            </Link>
            <Link href="/login" className="btn-ghost large">
              Sign in to your organization
            </Link>
          </div>
          <div className="hero-note">
            <span><Check /> Human approval before any email sends</span>
            <span><Check /> Organization-scoped records</span>
            <span><Check /> Your own mailbox &amp; calendar</span>
          </div>
        </div>

        <div className="hero-panel" aria-hidden="true">
          <div className="hero-panel-inner">
            <div className="hero-panel-top">
              <span className="hero-panel-dots"><i /><i /><i /></span>
              <span className="hero-panel-title">Opportunity radar</span>
              <span className="hero-panel-badge">Live</span>
            </div>
            <div className="hero-rows">
              <div className="hero-row">
                <div>
                  <strong>Fleet operator expands regional depot</strong>
                  <small>Operational signal · Logistics · Watchlist</small>
                </div>
                <div className="score">
                  <span className="score-bar"><i style={{ width: "86%" }} /></span>
                  <span className="score-val">86</span>
                </div>
              </div>
              <div className="hero-row">
                <div>
                  <strong>OEM announces new assembly line</strong>
                  <small>Production signal · Manufacturing</small>
                </div>
                <div className="score">
                  <span className="score-bar"><i style={{ width: "74%" }} /></span>
                  <span className="score-val">74</span>
                </div>
              </div>
              <div className="hero-row">
                <div>
                  <strong>Tier-1 supplier reports emission targets</strong>
                  <small>Compliance signal · Sustainability</small>
                </div>
                <div className="score">
                  <span className="score-bar cool"><i style={{ width: "61%" }} /></span>
                  <span className="score-val">61</span>
                </div>
              </div>
            </div>
            <div className="hero-panel-foot">
              <span>Scored with a transparent points breakdown</span>
              <b>Evidence attached</b>
            </div>
          </div>
        </div>
      </section>

      <div className="stack-strip">
        <div className="stack-strip-inner">
          <span className="stack-strip-label">Works with</span>
          <div className="stack-strip-items">
            {stack.map(item => (
              <span key={item} className="stack-chip">{item}</span>
            ))}
          </div>
        </div>
      </div>

      <section className="landing-section tight" aria-labelledby="flow-title">
        <div className="section-head">
          <span className="section-kicker">How it works</span>
          <h2 id="flow-title" className="mkt-title">
            One loop from list to closed deal
          </h2>
          <p className="section-copy">
            Every stage keeps its sources, approvals and history, so sales can move quickly without losing
            accountability.
          </p>
        </div>
        <div className="flow-grid">
          {flow.map((step, index) => (
            <article key={step.title} className="flow-step">
              <span className="flow-index">{String(index + 1).padStart(2, "0")}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="features" className="landing-section" aria-labelledby="features-title">
        <div className="section-head">
          <span className="section-kicker">Platform</span>
          <h2 id="features-title" className="mkt-title">
            Engineered for modern enterprise sales teams
          </h2>
          <p className="section-copy">
            Everything you need to find, research, reach and close high-value accounts — without stitching
            together six disconnected tools.
          </p>
        </div>
        <div className="feature-grid">
          {features.map(feature => (
            <article key={feature.title} className="feature-card">
              <span className={`feature-icon tone-${feature.tone}`}>
                <Icon name={feature.icon} />
              </span>
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="outreach" className="landing-section" aria-labelledby="outreach-title">
        <div className="split">
          <div className="split-copy">
            <span className="section-kicker">Outreach &amp; email</span>
            <h2 id="outreach-title">Personal, approved, and sent from your own mailbox</h2>
            <p>
              Sequence drafts are generated from reviewed research facts, then held for human approval. Sending
              runs through your connected Gmail or Outlook account, with unsubscribe, suppression and inbox
              checks in front of every attempt.
            </p>
            <ul className="check-list">
              <li><Check /> Exact-draft approval, with edits invalidating approval</li>
              <li><Check /> Independent recipient threads — never shared CC or BCC</li>
              <li><Check /> Replies, opt-outs and hard bounces stop follow-ups automatically</li>
              <li><Check /> Rolling send budget and clear SMTP-acceptance records</li>
            </ul>
          </div>
          <div className="mock-card" aria-hidden="true">
            <div className="mock-head">
              Draft review
              <span className="mock-pill">Awaiting approval</span>
            </div>
            <div className="mock-to">
              <span>To</span>
              <b>Logistics VP · example-manufacturing.com</b>
            </div>
            <div className="mock-body">
              Hi Priya,
              <br /><br />
              I noticed your Pune expansion adds two distribution hubs. Teams running multi-depot dispatch
              usually lose visibility between the yard and the line — <span className="hl">our TWMS pilot cut
              transit exceptions in a comparable network</span>.
              <br /><br />
              Worth a 20-minute review of the rollout plan?
            </div>
            <div className="mock-actions">
              <span className="mock-status"><i /> 3 cited facts attached</span>
              <span className="mock-mini-btn">Approve &amp; schedule</span>
            </div>
          </div>
        </div>
      </section>

      <section id="meetings" className="landing-section" aria-labelledby="meetings-title">
        <div className="split flip">
          <div className="split-copy">
            <span className="section-kicker">Meetings copilot</span>
            <h2 id="meetings-title">From booked call to reviewed minutes</h2>
            <p>
              Publish a booking page, aggregate organizer availability across Google and Outlook, and turn the
              call itself into structured follow-up — transcript, minutes of meeting and owned action items.
            </p>
            <ul className="check-list">
              <li><Check /> Public booking with holds and conflict-safe confirmation</li>
              <li><Check /> Teams and Google Meet creation with calendar invitations</li>
              <li><Check /> Recording and transcript retrieval when the tenant allows it</li>
              <li><Check /> Reviewed follow-up drafts and tracked action items</li>
            </ul>
          </div>
          <div className="mock-card" aria-hidden="true">
            <div className="mock-head">
              Discovery call · 30 min
              <span className="mock-pill">Recorded</span>
            </div>
            <div className="mock-note">
              <div className="mock-note-row"><b>Context</b><span>Multi-depot rollout, Pune and Chennai hubs</span></div>
              <div className="mock-note-row"><b>Problem</b><span>Yard congestion delays line-haul dispatch windows</span></div>
              <div className="mock-note-row"><b>Decision</b><span>Pilot TWMS at one hub, review in 30 days</span></div>
              <div className="mock-note-row"><b>Next step</b><span>Send pilot scope and pricing by Friday</span></div>
            </div>
            <div className="mock-tags">
              <span className="mock-tag">Action item · owner assigned</span>
              <span className="mock-tag">Transcript linked</span>
              <span className="mock-tag">Zoho deal updated</span>
            </div>
          </div>
        </div>
      </section>

      <div className="stats-band">
        <div className="stats-band-inner">
          <div className="stat-block">
            <strong>6</strong>
            <span>Solwer products mapped to market signals</span>
          </div>
          <div className="stat-block">
            <strong>62</strong>
            <span>Automotive sources monitored on a schedule</span>
          </div>
          <div className="stat-block">
            <strong>7</strong>
            <span>Research extraction roles behind each report</span>
          </div>
          <div className="stat-block">
            <strong>2</strong>
            <span>Meeting providers — Teams and Google Meet</span>
          </div>
        </div>
      </div>

      <section id="about" className="landing-section" aria-labelledby="cta-title">
        <div className="cta-panel">
          <h2 id="cta-title">Ready to scale your sales prospecting?</h2>
          <p>
            Create an organization, invite your team and bring your first spreadsheet. Research, outreach and
            meetings all stay inside one accountable workspace.
          </p>
          <div className="cta-actions">
            <Link href={signedIn ? "/dashboard" : "/register"} className="btn-cta large">
              {signedIn ? "Open dashboard" : "Create your organization"} <span aria-hidden="true">→</span>
            </Link>
            <Link href={signedIn ? "/settings/profile" : "/login"} className="btn-ghost large">
              {signedIn ? "Account settings" : "Access an existing workspace"}
            </Link>
          </div>
        </div>
      </section>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <div className="footer-brand">
            <Link href="/" className="site-brand" aria-label="Solwer GTM home">
              <span className="site-brand-mark small">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 2.6 2.8 7.3 12 12l9.2-4.7L12 2.6Z" />
                  <path d="m2.8 16.7 9.2 4.7 9.2-4.7" />
                  <path d="m2.8 12 9.2 4.7 9.2-4.7" />
                </svg>
              </span>
              <span>
                <span className="site-brand-name">SOLWER <span className="site-brand-tag">GTM</span></span>
                <span className="site-brand-sub">Sales Intelligence Platform</span>
              </span>
            </Link>
            <p>
              A local-first GTM workspace for evidence-backed prospecting, human-approved outreach and
              accountable meeting follow-through.
            </p>
          </div>
          <div className="footer-col">
            <h4>Platform</h4>
            <a href="#features">Features</a>
            <a href="#outreach">Outreach &amp; email</a>
            <a href="#meetings">Meetings copilot</a>
          </div>
          <div className="footer-col">
            <h4>Workspace</h4>
            <Link href="/login">Sign in</Link>
            <Link href="/register">Create organization</Link>
            <Link href="/settings/integrations">Integrations</Link>
          </div>
          <div className="footer-col">
            <h4>Data &amp; safety</h4>
            <Link href="/login">Organization settings</Link>
            <Link href="/login">Team &amp; roles</Link>
            <Link href="/login">Email accounts</Link>
          </div>
        </div>
        <div className="footer-base">
          <span>&copy; {new Date().getFullYear()} Solwer GTM Sales Intelligence. All rights reserved.</span>
          <span>Multi-tenant SaaS · Human-reviewed outreach</span>
        </div>
      </footer>
    </div>
  );
}

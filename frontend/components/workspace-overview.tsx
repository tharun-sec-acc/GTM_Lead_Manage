"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { displayDate, intelligenceRequest as request, label, statusTone, type JobSummary, type Page } from "../lib/intelligence";
import UiIcon from "./ui-icon";

export default function WorkspaceOverview({ companies, domains, imports, loaded }: {
  companies: number; domains: number; imports: number; loaded: boolean;
}) {
  const [research, setResearch] = useState<Page<JobSummary> | null>(null);
  const [campaigns, setCampaigns] = useState<{ status: string }[] | null>(null);
  const [researchError, setResearchError] = useState("");
  const [campaignError, setCampaignError] = useState("");
  useEffect(() => {
    let active = true;
    void request<Page<JobSummary>>("/intelligence/research?limit=3")
      .then(result => { if (active) setResearch(result); })
      .catch(error => { if (active) setResearchError(error instanceof Error ? error.message : "Research history unavailable."); });
    void request<{ status: string }[]>("/campaigns")
      .then(result => { if (active) setCampaigns(result); })
      .catch(error => { if (active) setCampaignError(error instanceof Error ? error.message : "Campaign status unavailable."); });
    return () => { active = false; };
  }, []);
  return <>
    <header className="page-heading"><div><p className="eyebrow">YOUR CONNECTED PROSPECTING WORKSPACE</p>
      <h1>From company list to your next conversation.</h1>
      <p>Upload your Excel, find a company by domain, and turn reviewed research into relevant outreach.</p></div>
      <div className="actions"><a href="#companies" className="button-link secondary"><UiIcon name="search" size={16} /> Find a company</a>
        <a href="#import" className="button-link"><UiIcon name="upload" size={16} /> Import Excel</a></div>
    </header>
    <div className="dashboard-metrics">
      <div className="metric-card"><span className="metric-icon"><UiIcon name="companies" /></span><span>Company leads</span><strong>{loaded ? companies : "--"}</strong><small>Up to 1,000 loaded companies</small></div>
      <div className="metric-card"><span className="metric-icon violet"><UiIcon name="link" /></span><span>With a saved domain</span><strong>{loaded ? domains : "--"}</strong><small>{loaded ? `${companies - domains} need domain review` : "Loading company domains"}</small></div>
      <div className="metric-card"><span className="metric-icon amber"><UiIcon name="upload" /></span><span>Recent Excel imports</span><strong>{loaded ? imports : "--"}</strong><small>Up to 100 recent imports</small></div>
      <div className="metric-card"><span className="metric-icon blue"><UiIcon name="mail" /></span><span>Active campaigns</span><strong>{campaigns ? campaigns.filter(item => item.status === "active").length : "--"}</strong><small>Approvals and inbox checks still apply</small></div>
    </div>
    {campaignError && <p role="alert" className="error">Campaign status: {campaignError}</p>}
    <nav className="workspace-journey" aria-label="Prospecting workflow">
      <a href="#import"><span>01</span><strong>Upload Excel</strong><small>Map sheets and review imports</small></a>
      <a href="#companies"><span>02</span><strong>Find your company</strong><small>Search by name or domain</small></a>
      <a href="#company-workbench"><span>03</span><strong>Research & find people</strong><small>Select a company to continue below</small></a>
      <Link href="/followups"><span>04</span><strong>Review & reach out</strong><small>Independent, approved email threads</small></Link>
    </nav>
    <details className="workspace-recent"><summary><UiIcon name="spark" size={16} /> Research activity
      {research && <span className="count-badge">{research.total} jobs</span>}</summary>
      {researchError && <p role="alert" className="error">{researchError}</p>}
      {research?.items.map(job => <Link key={job.id} className="activity-row" href={`/intelligence/jobs/${encodeURIComponent(job.id)}`}>
        <span className="activity-icon"><UiIcon name="spark" size={18} /></span><span><strong>{job.company_name}</strong><small>{job.domain} · {displayDate(job.created_at)}</small></span>
        <span className={`status-pill ${statusTone(job.status)}`}>{label(job.status)}</span></Link>)}
      {!researchError && !research?.items.length && <p>{research ? "No research yet. Choose an imported company below, or start standalone research." : "Loading research history..."}</p>}
      <Link className="text-link" href="/intelligence">Open standalone intelligence <UiIcon name="arrow" size={15} /></Link>
    </details>
  </>;
}

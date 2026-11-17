"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchProductLeads,
  fetchProductResearch,
  type ProductLead,
  type ProductResearchJob,
} from "../lib/products";
import { useProduct } from "./product-workspace";
import UiIcon from "./ui-icon";

export default function ProductResearch() {
  const product = useProduct();
  const [jobs, setJobs] = useState<ProductResearchJob[]>([]);
  const [leads, setLeads] = useState<ProductLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setJobs([]);
    setLeads([]);
    Promise.all([fetchProductResearch(product.id), fetchProductLeads(product.id)])
      .then(([researchJobs, productLeads]) => {
        if (cancelled) return;
        setJobs(researchJobs);
        setLeads(productLeads);
      })
      .catch((error: Error) => { if (!cancelled) setError(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  const researchedLeadIds = new Set(jobs.map((job) => job.lead_id).filter(Boolean));
  const companyName = (leadId: string | null) =>
    leads.find((lead) => lead.lead_id === leadId)?.company_name ?? "Company";

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">RESEARCH</p>
          <h1>Company research</h1>
          <p>
            Company facts are collected once and shared across products. Product opportunity analysis is
            separate and always starts as a draft.
          </p>
        </div>
      </div>

      {error && <div role="alert" className="alert">{error}</div>}

      {loading ? (
        <div className="empty-state"><p>Loading research…</p></div>
      ) : (
        <>
          <h3>Research jobs</h3>
          {jobs.length === 0 ? (
            <div className="empty-state">
              <UiIcon name="spark" size={26} />
              <h3>No research jobs for this product's companies</h3>
              <p>Open a company below to run bounded, cited research from the dashboard workbench.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Status</th>
                    <th>Stage</th>
                    <th>Facts</th>
                    <th>Sources</th>
                    <th>Started</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        {job.lead_id ? (
                          <Link href={`/leads/${encodeURIComponent(job.lead_id)}`}>{companyName(job.lead_id)}</Link>
                        ) : "Standalone company"}
                      </td>
                      <td><span className="badge">{job.status}</span></td>
                      <td>{job.stage} · {job.progress}%</td>
                      <td>{job.facts_count}</td>
                      <td>{job.sources_count}</td>
                      <td>{new Date(job.created_at).toLocaleString()}</td>
                      <td><Link className="button-link secondary" href={`/intelligence/jobs/${job.id}`}>Open report</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3>Companies in this product</h3>
          {leads.length === 0 ? <p>No companies associated yet.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Company</th><th>Domain</th><th>Research</th><th /></tr></thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <Link href={`/leads/${encodeURIComponent(lead.lead_id)}`}>{lead.company_name}</Link>
                      </td>
                      <td>{lead.domain || "Not confirmed"}</td>
                      <td>
                        <span className="badge">{researchedLeadIds.has(lead.lead_id) ? "Has a research job" : "Not researched"}</span>
                      </td>
                      <td>
                        <Link
                          className="button-link secondary"
                          href={`/?lead=${encodeURIComponent(lead.lead_id)}#company-workbench`}
                        >
                          Run research
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  createProductCampaign,
  fetchProductCampaigns,
  type ProductCampaign,
} from "../lib/products";
import { useProduct } from "./product-workspace";

export default function ProductCampaigns() {
  const product = useProduct();
  const [campaigns, setCampaigns] = useState<ProductCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"manual" | "automatic">("manual");
  const [delays, setDelays] = useState("3, 4, 5");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setCampaigns([]);
    fetchProductCampaigns(product.id)
      .then((items) => { if (!cancelled) setCampaigns(items); })
      .catch((error: Error) => { if (!cancelled) setMessage(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  function parseDelays(): number[] {
    return delays
      .split(/[,;\s]+/)
      .filter(Boolean)
      .map(Number);
  }

  async function create() {
    const parsed = parseDelays();
    setBusy(true);
    setMessage("");
    try {
      if (parsed.length > 5 || parsed.some((day) => !Number.isInteger(day) || day < 1 || day > 365)) {
        throw new Error("Use zero to five whole-day delays between 1 and 365.");
      }
      const created = await createProductCampaign(product.id, { name: name.trim(), mode, delays: parsed });
      setCampaigns((current) => [created, ...current]);
      setName("");
      setMessage("Draft campaign created. Add recipients and approve drafts before activating.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create the campaign.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CAMPAIGNS</p>
          <h1>Campaigns</h1>
          <p>
            Campaigns for {product.name}. Every recipient keeps an independent thread, and drafts still
            require exact review and approval.
          </p>
        </div>
      </div>

      {message && <div role="alert" className="alert">{message}</div>}

      <div className="detail">
        <h3>New draft campaign</h3>
        <div className="grid">
          <label>Name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Q1 outreach" /></label>
          <label>
            Mode
            <select value={mode} onChange={(event) => setMode(event.target.value as "manual" | "automatic")}>
              <option value="manual">Manual approval per message</option>
              <option value="automatic">Automatic follow-ups (approved sequence)</option>
            </select>
          </label>
          <label>
            Follow-up delays (days)
            <input value={delays} onChange={(event) => setDelays(event.target.value)} placeholder="3, 4, 5" />
          </label>
        </div>
        <button disabled={busy || !name.trim()} onClick={() => void create()}>Create draft campaign</button>
        <p className="field-help">
          Creating a campaign sends nothing. Adding recipients, generating drafts, approving and activating
          remain separate, explicit steps.
        </p>
      </div>

      {loading ? (
        <div className="empty-state"><p>Loading campaigns…</p></div>
      ) : campaigns.length === 0 ? (
        <div className="empty-state"><h3>No campaigns for this product</h3><p>Create a draft campaign above.</p></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Mode</th>
                <th>Delays</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {campaigns.map((campaign) => (
                <tr key={campaign.id}>
                  <td><strong>{campaign.name}</strong></td>
                  <td>{campaign.mode}</td>
                  <td>{campaign.delays.length ? campaign.delays.join(", ") : "No follow-ups"}</td>
                  <td><span className="badge">{campaign.status}</span></td>
                  <td><Link className="button-link secondary" href="/followups">Open outreach</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

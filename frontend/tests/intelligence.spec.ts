import { expect, test, type Page } from "@playwright/test";
import type { ResearchFact, ResearchJob, ResearchReport, ResearchSource } from "../lib/intelligence";

const source: ResearchSource = {
  id: "source-test", url: "https://example.com/report", title: "Synthetic company report",
  domain: "example.com", publisher: "Synthetic Company", published_at: "2026-10-10T00:00:00Z",
  retrieved_at: "2026-11-16T00:00:00Z", content_hash: "synthetic-hash", category: "official",
  reliability: "official", retrieval_method: "http",
  excerpt: "Synthetic Company manufactures test components. Revenue was INR 100 million in FY2026.",
};
const citation = {
  source_id: source.id, url: source.url, title: source.title, excerpt: source.excerpt, page_number: 12,
  retrieved_at: source.retrieved_at, published_at: source.published_at, reliability: source.reliability,
};
const facts: ResearchFact[] = [
  { id: "fact-company", category: "company", field_name: "business_model", value: "Synthetic Company manufactures test components.",
    unit: null, currency: null, reporting_period: null, entity_scope: "Synthetic Company",
    verification_status: "reported", confidence: .8, citations: [citation] },
  { id: "fact-financial", category: "financial", field_name: "annual_revenue", value: "100",
    unit: "million", currency: "INR", reporting_period: "FY2026", entity_scope: "Standalone",
    verification_status: "reported", confidence: .8, citations: [citation] },
  { id: "fact-news", category: "news", field_name: "product_launch", value: "Synthetic test announcement.",
    unit: null, currency: null, reporting_period: null, entity_scope: "Synthetic Company",
    verification_status: "reported", confidence: .7, citations: [citation] },
];
const lead = { id: "lead-test", company_name: "Synthetic Company", domain: "example.com", industry: "Manufacturing",
  location: null, designation: null, revenue: null, email: null, phone: null, remarks: null, key_person_info: null, extra: {} };
const contact = { id: "contact-test", name: "Alex Test", title: "Director", email: "alex@example.com",
  source: "Manual", verification_status: "unverified", is_key_decision_maker: false };

async function mockApi(page: Page, existingResearch = false) {
  const state = {
    created: existingResearch, polls: 0, retried: false, canceled: false,
    researchRequests: [] as unknown[], generationRequests: [] as unknown[],
    message: { id: "message-test", step_number: 0, subject: "", body: "", status: "draft", due_at: null,
      sent_at: null, approved_at: null, message_id: "synthetic-message", last_error: null, manual_reply: false, events: [] },
  };
  const campaign = { id: "campaign-test", name: "Synthetic outreach", mode: "manual", delays: [], status: "draft",
    sequence_approved_at: null, enrollments: [{ id: "enrollment-test", lead_id: lead.id, company_name: lead.company_name,
      contact_id: contact.id, contact_name: contact.name, recipient: contact.email, status: "active",
      reply_blocked: false, messages: [state.message], replies: [] }] };
  function job(): ResearchJob {
    const status = state.canceled ? "cancelled" : state.polls < 2 ? "running" : state.retried ? "completed" : "partial";
    return {
      id: "job-test", company_id: "company-test", company_name: lead.company_name, domain: lead.domain, lead_id: lead.id,
      status, progress: status === "running" ? 60 : 100, created_at: "2026-11-16T00:00:00Z",
      updated_at: "2026-11-16T00:00:00Z", stage: status === "running" ? "collecting_sources" : "finished",
      error: null, sources_count: 1, pages_processed: 1, facts_count: 3, report_id: status === "running" ? null : "report-test",
      agents: ["company", "news", "financial", "funding", "leadership", "competitors", "signals", "verification", "synthesis"]
        .map(agent => ({ id: agent, agent, status: agent === "news" && !state.retried ? "failed" : "completed",
          progress: 100, error: agent === "news" && !state.retried ? "Synthetic provider failure" : null,
          retry_count: state.retried ? 1 : 0, started_at: null, finished_at: null })),
    };
  }
  await page.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== "http://localhost:8000") return route.continue();
    const pathname = url.pathname;
    let response: unknown;
    let status = 200;
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,PUT", "Access-Control-Allow-Headers": "Content-Type" } });
    }
    if (pathname === "/intelligence/status") {
      response = { enabled: true, search_provider: "official_site", search_configured: false, model_configured: true, note: "Synthetic test" };
    } else if (pathname === "/intelligence/research" && request.method() === "POST") {
      state.created = true; state.polls = 0; state.canceled = false;
      state.researchRequests.push(request.postDataJSON());
      response = { job_id: "job-test", company_id: "company-test", reused: false }; status = 202;
    } else if (pathname === "/intelligence/research") {
      response = { items: state.created ? [job()] : [], total: state.created ? 1 : 0 };
    } else if (pathname === "/intelligence/research/job-test") {
      state.polls++; response = job();
    } else if (pathname === "/intelligence/research/job-test/retry") {
      state.retried = true; state.polls = 0; response = job();
    } else if (pathname === "/intelligence/research/job-test/cancel") {
      state.canceled = true; response = job();
    } else if (pathname === "/intelligence/companies/company-test/facts") {
      response = { items: facts, total: facts.length };
    } else if (pathname === "/intelligence/companies/company-test/sources") {
      response = { items: [source], total: 1 };
    } else if (pathname === "/intelligence/reports/report-test") {
      const report: ResearchReport = { id: "report-test", company_id: "company-test", job_id: "job-test",
        version: state.retried ? 2 : 1, created_at: "2026-11-16T00:00:00Z", summary: facts[0].value,
        sections: [{ category: "company", title: "Company overview", status: "reported",
          fact_ids: ["fact-company"], text: facts[0].value }], limitations: ["Synthetic browser fixtures only."] };
      response = report;
    } else if (pathname === "/integrations/bedrock/profiles") {
      response = { profiles: [{ id: "test-profile", arn: "test-approved-profile", name: "Approved test profile",
        type: "APPLICATION", regions: ["us-east-1"] }], next_token: null };
    } else if (pathname === "/integrations/bedrock/status") {
      response = { configured: true, region: "us-east-1", model_id: "test-model", note: "Synthetic model" };
    } else if (pathname === "/leads") {
      response = [lead];
    } else if (pathname === "/leads/lead-test/contacts") {
      response = [contact];
    } else if (pathname === "/leads/lead-test/apollo/search-results") {
      response = [];
    } else if (pathname === "/leads/lead-test/profile") {
      response = { lead, overview: { contact_count: 1, email_count: 0, reply_count: 0, meeting_count: 0,
        lifecycle_stage: null, owner: null }, contacts: [contact], email_history: [], replies: [],
        meetings: { implemented: false, items: [] }, company_research: { implemented: false, items: [] },
        commercial_lifecycle: { implemented: false, items: [] }, timeline: [], timeline_limit: 200 };
    } else if (pathname === "/campaigns") {
      response = [campaign];
    } else if (pathname === "/campaigns/campaign-test") {
      response = campaign;
    } else if (pathname === "/campaigns/campaign-test/analytics") {
      response = { recipient_count: 1, active_recipient_count: 1, stopped_recipient_count: 0,
        suppressed_recipient_count: 0, replied_recipient_count: 0, accepted_recipient_count: 0,
        accepted_email_count: 0, opened_recipient_count: 0, clicked_recipient_count: 0,
        reply_rate_percent: null, open_rate_percent: null, click_rate_percent: null, engagement_note: "Synthetic analytics" };
    } else if (pathname === "/enrollments/enrollment-test/generate") {
      state.generationRequests.push(request.postDataJSON());
      state.message.subject = "Cited introduction"; state.message.body = "Synthetic evidence-backed draft.";
      response = [state.message];
    } else if (pathname === "/mailbox/status") {
      response = { last_success_at: "2026-11-16T00:00:00Z", last_error: null };
    } else if (pathname === "/mailbox/capacity") {
      response = { window_hours: 24, configured_limit: 50, attempts_counted: 0, remaining_application_budget: 50,
        sending_enabled: false, unsubscribe_enabled: true, tracking_enabled: false, tracking_configured: false,
        tracking_note: "Synthetic tracking disabled", note: "Synthetic budget" };
    } else if (["/batches", "/replies/unmatched", "/sales-tasks"].includes(pathname)) {
      response = [];
    } else {
      throw new Error(`Unexpected API request in isolated browser test: ${request.method()} ${pathname}`);
    }
    return route.fulfill({ status, json: response, headers: { "Access-Control-Allow-Origin": "*" } });
  });
  return state;
}

test("research uses explicit configuration and renders persisted progress, financial evidence and retry", async ({ page }) => {
  const state = await mockApi(page);
  await page.goto("/intelligence");
  await page.getByRole("textbox", { name: "Company name", exact: true }).fill("Synthetic Company");
  await page.getByRole("textbox", { name: "Official website or domain", exact: true }).fill("example.com");
  await page.getByRole("radio", { name: /Comprehensive research/ }).check();
  await expect(page.getByRole("button", { name: "Start research", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Load AWS profiles", exact: true }).click();
  await page.getByRole("combobox", { name: "Research inference profile" }).selectOption("test-approved-profile");
  await page.getByRole("checkbox", { name: /I confirm this public-company research/ }).check();
  await page.getByRole("button", { name: "Start research", exact: true }).click();
  await expect(page.getByRole("progressbar", { name: "Overall research progress" })).toHaveAttribute("value", "60");
  expect(state.researchRequests[0]).toMatchObject({ depth: "comprehensive", inference_profile_id: "test-approved-profile" });
  await expect(page.getByRole("button", { name: "Retry failed work" })).toBeVisible({ timeout: 10000 });
  await page.getByRole("button", { name: "Financials", exact: true }).click();
  await expect(page.getByRole("cell", { name: "100 INR · million", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "FY2026", exact: true })).toBeVisible();
  await page.locator(".financial-table .citation-details > summary").click();
  await expect(page.getByRole("link", { name: /Synthetic company report/ })).toHaveAttribute("href", source.url);
  await page.getByRole("button", { name: "News & developments", exact: true }).click();
  await page.getByRole("textbox", { name: "Published from", exact: true }).fill("2026-10-11");
  await expect(page.getByRole("heading", { name: "No findings match these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Retry failed work" }).click();
  await expect(page.getByText("Report version 2 ·", { exact: false })).toBeVisible({ timeout: 10000 });
  await page.getByRole("button", { name: "New research", exact: true }).click();
  await page.getByRole("checkbox", { name: /I confirm this public-company research/ }).check();
  await page.getByRole("button", { name: "Start research", exact: true }).click();
  await page.getByRole("button", { name: "Cancel research", exact: true }).click();
  await expect(page.locator(".research-progress .section-title > .status-pill")).toHaveText("Cancelled");
});

test("Lead 360 passes only selected research IDs to draft generation without approving mail", async ({ page }) => {
  const state = await mockApi(page, true);
  await page.goto("/leads/lead-test");
  await expect(page.locator(".lead-intelligence-section")).toBeVisible();
  await page.getByRole("button", { name: /Synthetic outreach/ }).click();
  await page.locator(".outreach-research-picker > summary").click();
  await page.getByRole("checkbox", { name: /Business model Synthetic Company manufactures/ }).check();
  await page.getByRole("textbox", { name: "Approved company and DENSO product facts", exact: true }).fill("Use the approved offering and ask for an introduction.");
  await page.getByRole("button", { name: "Generate this recipient's drafts", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Subject", exact: true })).toHaveValue("Cited introduction");
  expect(state.generationRequests[0]).toMatchObject({ research_fact_ids: ["fact-company"] });
  await expect(page.getByRole("button", { name: "Approve saved email", exact: true })).toBeEnabled();
  expect(state.message.status).toBe("draft");
});

test("mobile navigation, company search and the Apollo review deep link preserve the existing flow", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Companies & leads", exact: true }).click();
  await expect(page.getByRole("button", { name: "Toggle navigation" })).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("searchbox", { name: "Search companies" }).fill("no-match");
  await expect(page.getByRole("heading", { name: "No matching companies" })).toBeVisible();
  await page.goto("/?lead=lead-test#companies");
  await expect(page.getByRole("heading", { name: "Selected contacts", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Search Apollo", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("Apollo enrichment keeps explicit employer confirmation without a blocking browser popup", async ({ page }) => {
  await mockApi(page);
  let enriched: unknown;
  await page.route("**/leads/lead-test/apollo/search-results", route => route.fulfill({ json: [{
    id: "apollo-test", name: "Alex T.", title: "Director", department: null, seniority: "director",
    organization: "Synthetic Company", organization_domain: null, organization_matches: false,
    linkedin_url: null, has_email: true, retrieved_at: "2026-11-16T00:00:00Z",
  }], headers: { "Access-Control-Allow-Origin": "*" } }));
  await page.route("**/leads/lead-test/apollo/enrich", route => {
    enriched = route.request().postDataJSON();
    return route.fulfill({ json: contact, headers: { "Access-Control-Allow-Origin": "*" } });
  });
  await page.goto("/?lead=lead-test#companies");
  await expect(page.getByRole("button", { name: "Select & enrich", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: "I checked that this person currently works at Synthetic Company.", exact: true }).check();
  await page.getByRole("button", { name: "Select & enrich", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Contact saved." })).toBeVisible();
  expect(enriched).toMatchObject({ apollo_id: "apollo-test", organization_confirmed: true });
});

test("combined dashboard searches imported domains and saves a domain without calling Apollo", async ({ page }) => {
  const state = await mockApi(page);
  let saved: unknown;
  await page.route("**/leads/lead-test/domain", route => {
    saved = route.request().postDataJSON();
    return route.fulfill({ json: { ...lead, domain: "example.com" }, headers: { "Access-Control-Allow-Origin": "*" } });
  });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Upload your spreadsheet" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Search companies" }).fill("example.com");
  await expect(page.locator("#companies tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await page.getByRole("textbox", { name: "Confirmed company domain or website" }).fill("https://www.example.com/");
  await page.getByRole("button", { name: "Save domain", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Company domain saved." })).toBeVisible();
  expect(saved).toEqual({ domain: "https://www.example.com/" });
  await page.getByRole("button", { name: "Company research", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Company name", exact: true })).toHaveValue("Synthetic Company");
  await expect(page.getByRole("textbox", { name: "Official website or domain", exact: true })).toHaveValue("example.com");
  expect(state.researchRequests).toHaveLength(0);
  await expect(page.getByRole("button", { name: "Start research", exact: true })).toBeDisabled();
});

test("Excel upload and mapping continue into domain search in the same dashboard", async ({ page }) => {
  const state = await mockApi(page);
  let imported = false;
  const headers = { "Access-Control-Allow-Origin": "*" };
  await page.route("**/batches", route => route.fulfill({
    headers, json: route.request().method() === "POST"
      ? { id: "batch-test", row_count: 1, headers: ["Company name", "Domain"], sheets: [
        { name: "Companies", headers: ["Company name", "Domain"], row_count: 1, column_count: 2,
          preview: [{ "Company name": lead.company_name, Domain: lead.domain }] },
      ] }
      : imported ? [{ id: "batch-test", filename: "synthetic.xlsx", status: "completed" }] : [],
  }));
  await page.route("**/leads", route => route.fulfill({ headers, json: imported ? [lead] : [] }));
  await page.route("**/batches/batch-test/start", route => {
    expect(route.request().postDataJSON().mapping.Companies).toMatchObject({ company_name: "Company name", domain: "Domain" });
    imported = true;
    return route.fulfill({ headers, json: { id: "batch-test", filename: "synthetic.xlsx", status: "completed", counts: { imported: 1 } } });
  });
  await page.goto("/");
  await expect(page.locator('input[type="file"]')).toBeHidden();
  await page.locator('input[type="file"]').setInputFiles({
    name: "synthetic.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("Synthetic upload fixture; API parsing is mocked."),
  });
  await page.getByRole("button", { name: "Start import", exact: true }).click();
  await page.getByRole("link", { name: "Find your imported companies", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search companies" }).fill("example.com");
  await page.locator("#companies tbody").getByRole("link", { name: "Research", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Company name", exact: true })).toHaveValue(lead.company_name);
  expect(state.researchRequests).toHaveLength(0);
});

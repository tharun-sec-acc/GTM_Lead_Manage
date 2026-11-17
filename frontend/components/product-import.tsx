"use client";

import { useEffect, useRef, useState } from "react";
import { API, fetchProductBatches, type ProductBatch } from "../lib/products";
import { useProduct } from "./product-workspace";
import UiIcon from "./ui-icon";

const fields = [
  ["company_name", "Company name"],
  ["domain", "Company domain"],
  ["email", "Email ID"],
  ["revenue", "Revenue"],
  ["phone", "Contact number"],
  ["remarks", "Remarks"],
  ["key_person_info", "Key person contact info"],
  ["designation", "Designation"],
  ["industry", "Industry"],
  ["location", "Location"],
] as const;

type Field = typeof fields[number][0];

type Sheet = {
  name: string;
  headers: string[];
  row_count: number;
  column_count: number;
  preview: Record<string, string>[];
};

type Preview = { id: string; headers: string[]; sheets: Sheet[]; row_count: number };

type BatchReport = ProductBatch & {
  counts?: Record<string, number>;
  rows?: {
    sheet_name: string;
    row_number: number;
    status: string;
    message: string | null;
    original: Record<string, string>;
  }[];
};

function guessMapping(headers: string[]): Record<string, string> {
  const aliases: Record<Field, string[]> = {
    company_name: ["company name", "company"],
    domain: ["company domain", "domain"],
    email: ["email id", "email", "email address"],
    revenue: ["revenue"],
    phone: ["contact number", "phone", "phone number"],
    remarks: ["remarks", "notes"],
    key_person_info: ["key person contact info", "key person"],
    designation: ["designation", "job title", "title"],
    industry: ["industry"],
    location: ["location", "company location"],
  };
  return Object.fromEntries(
    fields.map(([field]) => [
      field,
      headers.find((header) => aliases[field].includes(header.trim().toLowerCase())) ?? "",
    ]),
  );
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export default function ProductImport() {
  const product = useProduct();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, Record<string, string>>>({});
  const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
  const [batches, setBatches] = useState<ProductBatch[]>([]);
  const [report, setReport] = useState<BatchReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  async function refreshBatches() {
    setBatches(await fetchProductBatches(product.id));
  }

  useEffect(() => {
    let cancelled = false;
    fetchProductBatches(product.id)
      .then((items) => { if (!cancelled) setBatches(items); })
      .catch((error: Error) => { if (!cancelled) setMessage(error.message); });
    return () => { cancelled = true; };
  }, [product.id]);

  useEffect(() => {
    if (!report?.id || report.status !== "pending") return;
    const timer = setInterval(async () => {
      try {
        const updated = await request<BatchReport>(`/batches/${report.id}`);
        setReport(updated);
        if (updated.status !== "pending") await refreshBatches();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not refresh the import.");
      }
    }, 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.id, report?.status]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unexpected error.");
    } finally {
      setBusy(false);
    }
  }

  function upload(file?: File) {
    if (!file) return;
    void run(async () => {
      const data = new FormData();
      data.append("file", file);
      data.append("product_id", product.id);
      const result = await request<Preview>("/batches", { method: "POST", body: data });
      setPreview(result);
      setMapping(Object.fromEntries(result.sheets.map((sheet) => [sheet.name, guessMapping(sheet.headers)])));
      setSelectedSheets(result.sheets.filter((sheet) => sheet.headers.length > 0).map((sheet) => sheet.name));
      setReport(null);
      await refreshBatches();
    });
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">IMPORT</p>
          <h1>Import companies</h1>
          <p>
            Companies imported here are associated with {product.name}. An existing master company is
            associated instead of duplicated.
          </p>
        </div>
      </div>

      {message && <div role="alert" className="alert">{message}</div>}

      <div
        className="dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          upload(event.dataTransfer.files[0]);
        }}
      >
        <span className="upload-icon"><UiIcon name="upload" size={25} /></span>
        <strong>Drop a company workbook here</strong>
        <p>.xlsx, up to 10 MB, 5,000 rows and 50 worksheets</p>
        <button disabled={busy} onClick={() => fileInput.current?.click()}>Choose file</button>
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx"
          hidden
          onChange={(event) => {
            upload(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>

      {preview && (
        <div className="mapping">
          <h3>Map worksheets · {preview.sheets.length} sheets · {preview.row_count} rows</h3>
          <p>Map the company name on every selected sheet. Unmapped columns stay on the lead record.</p>
          <div className="actions">
            <button
              disabled={busy}
              onClick={() => setSelectedSheets(preview.sheets.filter((sheet) => sheet.headers.length > 0).map((sheet) => sheet.name))}
            >
              Select all non-empty sheets
            </button>
            <button disabled={busy} onClick={() => setSelectedSheets([])}>Clear selection</button>
          </div>
          {preview.sheets.map((sheet) => {
            const selected = selectedSheets.includes(sheet.name);
            return (
              <div className="detail" key={sheet.name}>
                <label>
                  <input
                    type="checkbox"
                    disabled={!sheet.headers.length}
                    checked={selected}
                    onChange={(event) => setSelectedSheets(
                      event.target.checked
                        ? [...selectedSheets, sheet.name]
                        : selectedSheets.filter((name) => name !== sheet.name),
                    )}
                  />
                  {sheet.name} · {sheet.row_count} rows · {sheet.column_count} columns
                </label>
                {selected && (
                  <div className="grid">
                    {fields.map(([key, label]) => (
                      <label key={key}>
                        {label}{key === "company_name" && " *"}
                        <select
                          value={mapping[sheet.name]?.[key] ?? ""}
                          onChange={(event) => setMapping({
                            ...mapping,
                            [sheet.name]: { ...mapping[sheet.name], [key]: event.target.value },
                          })}
                        >
                          <option value="">Not mapped</option>
                          {sheet.headers.map((header) => <option key={header} value={header}>{header}</option>)}
                        </select>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <button
            disabled={busy || selectedSheets.length === 0 || selectedSheets.some((name) => !mapping[name]?.company_name)}
            onClick={() => void run(async () => {
              const selectedMappings = Object.fromEntries(selectedSheets.map((name) => [name, mapping[name]]));
              const result = await request<BatchReport>(`/batches/${preview.id}/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mapping: selectedMappings }),
              });
              setReport(result);
              setPreview(null);
              await refreshBatches();
            })}
          >
            Start import
          </button>
        </div>
      )}

      <h3>Product imports</h3>
      {batches.length === 0 ? <p>No imports for this product yet.</p> : (
        <div className="list">
          {batches.map((item) => (
            <button
              className="list-item"
              key={item.id}
              onClick={() => void run(async () => {
                if (item.status === "draft") {
                  const result = await request<Preview>(`/batches/${item.id}/preview`);
                  setPreview(result);
                  setMapping(Object.fromEntries(result.sheets.map((sheet) => [sheet.name, guessMapping(sheet.headers)])));
                  setSelectedSheets(result.sheets.filter((sheet) => sheet.headers.length > 0).map((sheet) => sheet.name));
                  setReport(null);
                } else {
                  setPreview(null);
                  setReport(await request<BatchReport>(`/batches/${item.id}`));
                }
              })}
            >
              <span>{item.filename}</span>
              <span className="badge">{item.status}</span>
            </button>
          ))}
        </div>
      )}

      {report && (
        <div className="detail">
          <h3>Import: {report.filename}</h3>
          <p>Status: <strong>{report.status}</strong>{report.status === "pending" && " (queued or processing)"}</p>
          {report.error && <p className="error">{report.error}</p>}
          {report.status === "failed" && (
            <button
              disabled={busy}
              onClick={() => void run(async () => {
                setReport(await request<BatchReport>(`/batches/${report.id}/retry`, { method: "POST" }));
                await refreshBatches();
              })}
            >
              Retry import
            </button>
          )}
          {report.counts && (
            <p>{Object.entries(report.counts).map(([key, value]) => `${key}: ${value}`).join(" · ")}</p>
          )}
          {report.rows?.filter((row) => row.status !== "imported").map((row) => (
            <details key={`${row.sheet_name}:${row.row_number}`}>
              <summary>{row.sheet_name} · Row {row.row_number}: {row.status} — {row.message}</summary>
              <pre>{JSON.stringify(row.original, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import {
  createTemplate,
  fetchTemplateVersions,
  fetchTemplates,
  previewTemplate,
  updateTemplate,
  TEMPLATE_TYPES,
  TEMPLATE_VARIABLES,
  type EmailTemplate,
  type TemplatePreview,
  type TemplateType,
  type TemplateVersion,
} from "../lib/templates";
import { useProduct } from "./product-workspace";

const VAR_PATTERN = /\{\{(\w+)\}\}/g;

function unknownVariables(subject: string, body: string): string[] {
  const allowed = new Set<string>(TEMPLATE_VARIABLES);
  const found = new Set<string>();
  for (const match of `${subject} ${body}`.matchAll(VAR_PATTERN)) found.add(match[1]);
  return [...found].filter((name) => !allowed.has(name));
}

export default function ProductTemplates() {
  const product = useProduct();
  const [productTemplates, setProductTemplates] = useState<EmailTemplate[]>([]);
  const [globalTemplates, setGlobalTemplates] = useState<EmailTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const [name, setName] = useState("");
  const [type, setType] = useState<TemplateType>("initial");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [basedOn, setBasedOn] = useState("");

  const [selected, setSelected] = useState<EmailTemplate | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [versions, setVersions] = useState<TemplateVersion[]>([]);
  const [preview, setPreview] = useState<TemplatePreview | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSelected(null);
    setPreview(null);
    Promise.all([fetchTemplates(product.id), fetchTemplates("global")])
      .then(([own, global]) => {
        if (cancelled) return;
        setProductTemplates(own);
        setGlobalTemplates(global);
      })
      .catch((error: Error) => { if (!cancelled) setMessage(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  const invalidVariables = useMemo(() => unknownVariables(subject, body), [subject, body]);

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

  function applyBase(templateId: string) {
    setBasedOn(templateId);
    const template = globalTemplates.find((item) => item.id === templateId);
    if (!template) return;
    setName(`${template.name} — ${product.name}`);
    setType(template.type);
    setSubject(template.subject_template);
    setBody(template.body_template);
  }

  function create() {
    void run(async () => {
      const created = await createTemplate({
        product_id: product.id,
        parent_template_id: basedOn || null,
        name: name.trim(),
        type,
        subject_template: subject,
        body_template: body,
      });
      setProductTemplates((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
      setName("");
      setSubject("");
      setBody("");
      setBasedOn("");
      setMessage(
        basedOn
          ? "Product override created as a new versioned template. The global template is unchanged."
          : "Product template created.",
      );
    });
  }

  function open(template: EmailTemplate) {
    setSelected(template);
    setEditSubject(template.subject_template);
    setEditBody(template.body_template);
    setPreview(null);
    setVersions([]);
    void run(async () => setVersions(await fetchTemplateVersions(template.id)));
  }

  function save() {
    if (!selected) return;
    void run(async () => {
      const updated = await updateTemplate(selected.id, {
        subject_template: editSubject,
        body_template: editBody,
      });
      setProductTemplates((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelected(updated);
      setVersions(await fetchTemplateVersions(updated.id));
      setMessage(`Saved version ${updated.version}. The previous version remains in history.`);
    });
  }

  function showPreview() {
    if (!selected) return;
    void run(async () => {
      setPreview(await previewTemplate(selected.id, {
        subject_template: editSubject,
        body_template: editBody,
      }));
    });
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TEMPLATES</p>
          <h1>Email templates</h1>
          <p>
            Global templates are shared. A product override is a separate versioned template and never
            changes the global original. Generated drafts still need approval.
          </p>
        </div>
      </div>

      {message && <div role="alert" className="alert">{message}</div>}

      <div className="detail">
        <h3>New {product.name} template</h3>
        <div className="grid">
          <label>
            Start from a global template (optional)
            <select value={basedOn} onChange={(event) => applyBase(event.target.value)}>
              <option value="">Blank template</option>
              {globalTemplates.map((template) => (
                <option key={template.id} value={template.id}>{template.name} · {template.type}</option>
              ))}
            </select>
          </label>
          <label>Name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Initial outreach" /></label>
          <label>
            Type
            <select value={type} onChange={(event) => setType(event.target.value as TemplateType)}>
              {TEMPLATE_TYPES.map((item) => <option key={item} value={item}>{item.replace(/_/g, " ")}</option>)}
            </select>
          </label>
        </div>
        <label>Subject<input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Hello {{contact_first_name}}" /></label>
        <label>Body<textarea rows={8} value={body} onChange={(event) => setBody(event.target.value)} /></label>
        <p className="field-help">Available variables: {TEMPLATE_VARIABLES.join(", ")}</p>
        {invalidVariables.length > 0 && (
          <p className="error">Unknown variables: {invalidVariables.join(", ")}</p>
        )}
        <button disabled={busy || !name.trim() || !subject.trim() || !body.trim() || invalidVariables.length > 0} onClick={create}>
          {basedOn ? "Create product override" : "Create product template"}
        </button>
      </div>

      {loading ? (
        <div className="empty-state"><p>Loading templates…</p></div>
      ) : (
        <>
          <h3>{product.name} templates</h3>
          {productTemplates.length === 0 ? <p>No product templates yet.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Type</th><th>Version</th><th>Source</th><th /></tr></thead>
                <tbody>
                  {productTemplates.map((template) => (
                    <tr key={template.id}>
                      <td><strong>{template.name}</strong></td>
                      <td>{template.type.replace(/_/g, " ")}</td>
                      <td>v{template.version}</td>
                      <td>{template.parent_template_id ? "Global override" : "Product"}</td>
                      <td><button className="secondary" onClick={() => open(template)}>Edit</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3>Global templates</h3>
          {globalTemplates.length === 0 ? <p>No global templates defined.</p> : (
            <div className="list">
              {globalTemplates.map((template) => (
                <div className="list-item" key={template.id}>
                  <span>{template.name} · {template.type.replace(/_/g, " ")} · v{template.version}</span>
                  <span className="badge">{template.is_active ? "active" : "inactive"}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {selected && (
        <div className="detail">
          <h3>{selected.name}</h3>
          <label>Subject<input value={editSubject} onChange={(event) => setEditSubject(event.target.value)} /></label>
          <label>Body<textarea rows={10} value={editBody} onChange={(event) => setEditBody(event.target.value)} /></label>
          <div className="actions">
            <button disabled={busy} onClick={save}>Save as new version</button>
            <button className="secondary" disabled={busy} onClick={showPreview}>Preview with sample values</button>
            <button className="secondary" onClick={() => { setSelected(null); setPreview(null); }}>Close</button>
          </div>
          {preview && (
            <div className="detail">
              <strong>Preview</strong>
              <p>{preview.subject}</p>
              <pre>{preview.body}</pre>
            </div>
          )}
          <h4>Version history</h4>
          {versions.length === 0 ? <p>No versions recorded.</p> : (
            <div className="list">
              {versions.map((version) => (
                <div className="list-item" key={version.id}>
                  <span>v{version.version} · {new Date(version.created_at).toLocaleString()}</span>
                  <span className="badge">{version.variables.length} variables</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

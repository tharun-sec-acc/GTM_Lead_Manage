"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { fetchProducts, type Product } from "../lib/products";
import UiIcon from "./ui-icon";

export default function ProductSelector() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    fetchProducts("active")
      .then(setProducts)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const activeSlug = pathname.match(/^\/products\/([^/]+)/)?.[1] ?? null;
  const activeProduct = products.find((p) => p.slug === activeSlug);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim() || !newSlug.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const response = await fetch("http://localhost:8000/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), slug: newSlug.trim() }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : `Failed (${response.status}).`);
      }
      const created = await response.json() as Product;
      setProducts((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setNewName(""); setNewSlug("");
      setOpen(false);
      router.push(`/products/${created.slug}`);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Failed to create product.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="product-selector" ref={ref}>
      <button
        className="product-selector-trigger secondary"
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={activeProduct ? `Product: ${activeProduct.name}` : "Select product"}
      >
        <span className="product-selector-dot" style={{ background: activeProduct?.primary_color ?? "var(--red)" }} />
        <span className="product-selector-label">
          {loading ? "Loading…" : activeProduct ? activeProduct.name : "All Products"}
        </span>
        <UiIcon name="arrow" size={14} />
      </button>

      {open && (
        <div className="product-selector-menu" role="listbox" aria-label="Select a product workspace">
          <Link
            href="/overview"
            className={`product-selector-item${!activeSlug ? " active" : ""}`}
            role="option"
            aria-selected={!activeSlug}
            onClick={() => setOpen(false)}
          >
            <span className="product-selector-dot" style={{ background: "#78808f" }} />
            Global Overview
          </Link>
          {error ? (
            <div className="product-selector-error">
              <span>{error}</span>
              <button onClick={() => { setError(null); setLoading(true); fetchProducts("active").then(setProducts).catch((e: Error) => setError(e.message)).finally(() => setLoading(false)); }}>
                Retry
              </button>
            </div>
          ) : (
            products.map((p) => (
              <Link
                key={p.id}
                href={`/products/${p.slug}`}
                className={`product-selector-item${activeSlug === p.slug ? " active" : ""}`}
                role="option"
                aria-selected={activeSlug === p.slug}
                onClick={() => setOpen(false)}
              >
                <span className="product-selector-dot" style={{ background: p.primary_color ?? "var(--red)" }} />
                {p.name}
              </Link>
            ))
          )}
          <div className="product-selector-divider" />
          {!creating ? (
            <button className="product-selector-item product-selector-add" onClick={() => setCreating(true)}>
              <UiIcon name="add" size={14} />
              Add product
            </button>
          ) : (
            <form onSubmit={handleCreate} className="product-selector-create">
              <input
                placeholder="Product name"
                value={newName}
                onChange={(e) => {
                  setNewName(e.target.value);
                  if (!newSlug || newSlug === newName.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "")) {
                    setNewSlug(e.target.value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, ""));
                  }
                }}
                required
                autoFocus
              />
              <input
                placeholder="slug (e.g. my-product)"
                value={newSlug}
                onChange={(e) => setNewSlug(e.target.value)}
                required
              />
              {createError && <div className="error" style={{ fontSize: 11 }}>{createError}</div>}
              <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                <button type="submit" disabled={creating} style={{ fontSize: 12, padding: "7px 12px" }}>Create</button>
                <button type="button" className="secondary" style={{ fontSize: 12, padding: "7px 12px" }} onClick={() => { setCreating(false); setCreateError(null); }}>Cancel</button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
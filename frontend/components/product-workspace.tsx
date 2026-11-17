"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { fetchProducts, type Product } from "../lib/products";

const ProductContext = createContext<Product | null>(null);

export function useProduct(): Product {
  const product = useContext(ProductContext);
  if (!product) throw new Error("useProduct must be used inside a product workspace.");
  return product;
}

export type ProductSection =
  | "overview" | "companies" | "import" | "research"
  | "contacts" | "lead360" | "campaigns" | "templates"
  | "meetings" | "analytics";

const sections: { id: ProductSection; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "companies", label: "Companies" },
  { id: "import", label: "Import" },
  { id: "research", label: "Research" },
  { id: "contacts", label: "Contacts" },
  { id: "campaigns", label: "Campaigns" },
  { id: "templates", label: "Templates" },
  { id: "meetings", label: "Meetings" },
  { id: "analytics", label: "Analytics" },
];

interface Props {
  slug: string;
  section: ProductSection;
  children: React.ReactNode;
}

export default function ProductWorkspace({ slug, section, children }: Props) {
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // Cancel any in-flight request when product slug changes
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setProduct(null);

    fetchProducts("active")
      .then((products) => {
        if (controller.signal.aborted) return;
        const found = products.find((p) => p.slug === slug);
        if (found) {
          setProduct(found);
        } else {
          setError(`Product "${slug}" not found.`);
        }
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [slug]);

  const basePath = `/products/${slug}`;

  if (loading) {
    return (
      <main>
        <div className="empty-state">
          <p>Loading product workspace…</p>
        </div>
      </main>
    );
  }

  if (error || !product) {
    return (
      <main>
        <div className="alert">{error ?? "Product not found."}</div>
      </main>
    );
  }

  const dot = product.primary_color ?? "var(--red)";

  return (
    <main>
      {/* Breadcrumb */}
      <nav className="product-breadcrumb" aria-label="Breadcrumb">
        <Link href="/">DENSO GTM</Link>
        <span className="breadcrumb-divider">/</span>
        <span style={{ color: dot, fontWeight: 600 }}>{product.name}</span>
        <span className="breadcrumb-divider">/</span>
        <span>{sections.find((s) => s.id === section)?.label ?? section}</span>
      </nav>

      {/* Product sub-navigation */}
      <nav className="product-subnav" aria-label="Product workspace navigation">
        {sections.map((s) => (
          <Link
            key={s.id}
            href={s.id === "overview" ? basePath : `${basePath}/${s.id}`}
            className={`product-subnav-item${section === s.id ? " active" : ""}`}
            aria-current={section === s.id ? "page" : undefined}
          >
            {s.label}
          </Link>
        ))}
      </nav>

      {/* Content */}
      <div className="product-workspace-content">
        <ProductContext.Provider value={product}>{children}</ProductContext.Provider>
      </div>
    </main>
  );
}
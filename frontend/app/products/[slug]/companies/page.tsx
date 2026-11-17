"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductCompanies from "../../../../components/product-companies";

export default function ProductCompaniesPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="companies">
      <ProductCompanies />
    </ProductWorkspace>
  );
}

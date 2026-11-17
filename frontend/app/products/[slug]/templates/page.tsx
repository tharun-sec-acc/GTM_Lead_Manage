"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductTemplates from "../../../../components/product-templates";

export default function ProductTemplatesPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="templates">
      <ProductTemplates />
    </ProductWorkspace>
  );
}

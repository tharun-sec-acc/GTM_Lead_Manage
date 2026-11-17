"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductResearch from "../../../../components/product-research";

export default function ProductResearchPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="research">
      <ProductResearch />
    </ProductWorkspace>
  );
}

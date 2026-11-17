"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductImport from "../../../../components/product-import";

export default function ProductImportPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="import">
      <ProductImport />
    </ProductWorkspace>
  );
}

"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductAnalytics from "../../../../components/product-analytics";

export default function ProductAnalyticsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="analytics">
      <ProductAnalytics />
    </ProductWorkspace>
  );
}

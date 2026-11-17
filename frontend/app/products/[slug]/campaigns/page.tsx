"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductCampaigns from "../../../../components/product-campaigns";

export default function ProductCampaignsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="campaigns">
      <ProductCampaigns />
    </ProductWorkspace>
  );
}

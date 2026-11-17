"use client";

import { use } from "react";
import ProductWorkspace from "../../../../components/product-workspace";
import ProductMeetings from "../../../../components/product-meetings";

export default function ProductMeetingsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <ProductWorkspace slug={slug} section="meetings">
      <ProductMeetings />
    </ProductWorkspace>
  );
}

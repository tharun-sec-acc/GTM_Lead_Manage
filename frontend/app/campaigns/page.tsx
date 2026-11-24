"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function CampaignsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/followups");
  }, [router]);

  return (
    <div style={{ padding: "40px", textAlign: "center", color: "#94a3b8" }}>
      <p>Redirecting to Outreach &amp; Campaigns...</p>
    </div>
  );
}

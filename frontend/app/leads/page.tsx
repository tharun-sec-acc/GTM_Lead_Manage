"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LeadsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard#companies");
  }, [router]);

  return (
    <div style={{ padding: "40px", textAlign: "center", color: "#94a3b8" }}>
      <p>Redirecting to Companies &amp; Leads workspace...</p>
    </div>
  );
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SettingsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/settings/organization");
  }, [router]);

  return (
    <div style={{ padding: "40px", textAlign: "center", color: "#94a3b8" }}>
      <p>Redirecting to Organization Settings...</p>
    </div>
  );
}

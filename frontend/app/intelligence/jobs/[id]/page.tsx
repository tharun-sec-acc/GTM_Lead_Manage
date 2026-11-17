"use client";

import { useParams } from "next/navigation";
import IntelligenceWorkspace from "../../../../components/intelligence-workspace";

export default function ResearchJobPage() {
  const { id } = useParams<{ id: string }>();
  return <main className="intelligence-page"><IntelligenceWorkspace initialJobId={id} /></main>;
}

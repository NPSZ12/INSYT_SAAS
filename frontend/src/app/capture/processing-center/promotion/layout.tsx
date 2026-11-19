import type { ReactNode } from "react";

/**
 * INSYT Promotion is an authenticated, project-scoped workflow.
 * Never serve a long-lived prerendered HTML shell for this route.
 */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function PromotionLayout({
  children,
}: {
  children: ReactNode;
}) {
  return children;
}
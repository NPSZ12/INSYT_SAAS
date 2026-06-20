"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import { apiGet } from "../../../lib/api";


type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

function ReviewBatchLandingPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";
  const docId = searchParams.get("doc") || "";

  const [message, setMessage] = useState("");
  const [user, setUser] = useState<StoredUser | null>(null);
  const [isResolving, setIsResolving] = useState(true);

  useEffect(() => {
    if (!clientId || !projectId || !docId) {
      return;
    }

    const params = new URLSearchParams();

    params.set("client", clientId);
    params.set("project", projectId);
    params.set("doc", docId);

    if (batchId) {
      params.set("batch", batchId);
      params.set("summarySet", batchId);
      params.set("mode", "summary-set");
    }

    router.replace(`/summaries/review/doc?${params.toString()}`);
  }, [router, clientId, projectId, batchId, docId]);

  

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  useEffect(() => {
    if (!clientId || !projectId || !user || docId) {
      return;
    }

    setIsResolving(true);
    setMessage("");

    apiGet(
      `/api/summaries/summary-sets/checked-out?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&username=${encodeURIComponent(user.username)}`
    )
      .then((response) => {
        const activeSummarySet =
          response.active_summary_set ||
          response.summary_sets?.[0];

        if (!activeSummarySet?.batch_summary_set_id) {
          setMessage("No Summary Set is currently checked out to you.");
          return;
        }

        const summarySetId = activeSummarySet.batch_summary_set_id;

        const params = new URLSearchParams();

        params.set("client", clientId);
        params.set("project", projectId);
        params.set("batch", summarySetId);
        params.set("summarySet", summarySetId);
        params.set("mode", "summary-set");

        router.replace(`/summaries/review/doc?${params.toString()}`);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load checked-out Summary Set.");
      })
      .finally(() => {
        setIsResolving(false);
      });
  }, [router, clientId, projectId, user]);

  if (!clientId || !projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Please select a Summaries project before starting review."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (docId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Opening Review"
            subtitle="Preparing the Summaries review workspace..."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (isResolving) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Opening Review"
            subtitle="Checking for your checked-out Summary Set..."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (message) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Summary Set Checked Out"
            subtitle={message}
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Opening Review"
          subtitle="Preparing the Summaries review workspace..."
        />
      </PageContainer>
    </AppShell>
  );
}

export default function ReviewBatchLandingPage() {
  return (
    <Suspense fallback={<div>Loading review batch...</div>}>
      <ReviewBatchLandingPageContent />
    </Suspense>
  );
}
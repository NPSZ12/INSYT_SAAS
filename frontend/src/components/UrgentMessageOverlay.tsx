"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import Button from "./Button";
import { apiGet, apiPost } from "../lib/api";

type StoredUser = {
  username: string;
  display_name?: string;
  role: string;
};

type UrgentMessage = {
  message_id: string;
  workspace: string;
  client_id: string;
  project_id: string;
  sender_display_name?: string;
  sender_username: string;
  message: string;
  created_at: string;
};

function getWorkspace(pathname: string, workspaceParam: string | null) {
  if (workspaceParam) return workspaceParam;

  if (pathname.startsWith("/summaries")) return "summaries";
  if (pathname.startsWith("/discovery")) return "discovery";
  if (pathname.startsWith("/capture")) return "capture";

  return "";
}

export default function UrgentMessageOverlay() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const workspace = getWorkspace(
    pathname,
    searchParams.get("workspace")
  );

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [user, setUser] = useState<StoredUser | null>(null);
  const [urgentMessages, setUrgentMessages] = useState<UrgentMessage[]>([]);

  const activeMessage = urgentMessages[0];

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  function loadUrgentMessages() {
    if (!workspace || !clientId || !projectId || !user) return;

    apiGet(
      `/api/messages/urgent?workspace=${encodeURIComponent(
        workspace
      )}&client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&username=${encodeURIComponent(
        user.username
      )}&role=${encodeURIComponent(user.role || "")}`
    )
      .then((response) => {
        setUrgentMessages(response.messages || []);
      })
      .catch((error) => {
        console.error("Failed to load urgent messages:", error);
      });
  }

  useEffect(() => {
    loadUrgentMessages();

    const timer = window.setInterval(loadUrgentMessages, 30000);

    return () => window.clearInterval(timer);
  }, [workspace, clientId, projectId, user]);

  function acknowledge() {
    if (!activeMessage || !user) return;

    apiPost("/api/messages/urgent/acknowledge", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      message_id: activeMessage.message_id,
      username: user.username,
      display_name: user.display_name || user.username,
    })
      .then(() => {
        setUrgentMessages((current) =>
          current.filter(
            (item) => item.message_id !== activeMessage.message_id
          )
        );
      })
      .catch((error) => {
        console.error("Failed to acknowledge urgent message:", error);
      });
  }

  if (!activeMessage) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 p-6">
      <div className="w-full max-w-2xl rounded-3xl border-2 border-red-600 bg-slate-950 p-8 shadow-2xl">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-600 text-2xl font-bold text-white">
            !
          </div>

          <div>
            <h2 className="text-2xl font-bold text-white">
              Urgent Message
            </h2>

            <p className="text-sm text-slate-400">
              From{" "}
              {activeMessage.sender_display_name ||
                activeMessage.sender_username}
            </p>
          </div>
        </div>

        <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <p className="whitespace-pre-wrap text-base leading-7 text-slate-100">
            {activeMessage.message}
          </p>
        </div>

        <p className="mb-6 text-sm text-slate-400">
          You must confirm this urgent message before continuing.
        </p>

        <div className="flex justify-end">
          <Button onClick={acknowledge}>
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}
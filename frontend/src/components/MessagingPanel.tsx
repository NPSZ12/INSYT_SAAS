"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import ContentCard from "./ContentCard";
import Button from "./Button";
import { apiGet, apiPost } from "../lib/api";

type Channel = "project" | "admin" | "private";

type StoredUser = {
  username: string;
  display_name?: string;
  role: string;
};

type MessageItem = {
  message_id: string;
  workspace: string;
  client_id: string;
  project_id: string;
  channel: Channel;
  sender_username: string;
  sender_display_name?: string;
  sender_role?: string;
  recipient_usernames?: string[];
  message: string;
  parent_message_id?: string;
  forwarded_from_message_id?: string;
  forwarded_from_sender?: string;
  forwarded_body?: string;
  created_at: string;
  important?: boolean;
  urgent?: boolean;
  acknowledged_by?: string[];
};

type MessagingPanelProps = {
  workspace: "capture" | "discovery" | "summaries";
};

const ADMIN_ROLES = [
  "QC",
  "TL",
  "RM",
  "Admin",
  "INSYT Admin",
  "CDS Admin",
];

const ADMIN_ALERT_ROLES = [
  "RM",
  "Admin",
  "INSYT Admin",
  "CDS Admin",
];

export default function MessagingPanel({
  workspace,
}: MessagingPanelProps) {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [user, setUser] = useState<StoredUser | null>(null);
  const [channel, setChannel] = useState<Channel>("project");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [messageText, setMessageText] = useState("");
  const [privateRecipients, setPrivateRecipients] = useState("");
  const [status, setStatus] = useState("");
  const [selectedMessage, setSelectedMessage] =
    useState<MessageItem | null>(null);

  const [replyToMessage, setReplyToMessage] =
    useState<MessageItem | null>(null);

  const [forwardMessage, setForwardMessage] =
    useState<MessageItem | null>(null);

  const [forwardChannel, setForwardChannel] =
    useState<Channel>("project");

  const [forwardRecipients, setForwardRecipients] = useState("");

  const canUseAdminChannel =
    user?.role && ADMIN_ROLES.includes(user.role);

  const canSendAlertMessage =
    user?.role && ADMIN_ALERT_ROLES.includes(user.role);

  const [important, setImportant] = useState(false);
  const [urgent, setUrgent] = useState(false);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  useEffect(() => {
    if (channel === "admin" && !canUseAdminChannel) {
      setChannel("project");
    }
  }, [channel, canUseAdminChannel]);

  useEffect(() => {
    setSelectedMessage(null);
    setReplyToMessage(null);
    setForwardMessage(null);
  }, [channel]);

  function loadMessages() {
    if (!clientId || !projectId || !user) return;

    apiGet(
      `/api/messages/?workspace=${encodeURIComponent(
        workspace
      )}&client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&channel=${encodeURIComponent(
        channel
      )}&username=${encodeURIComponent(
        user.username
      )}&role=${encodeURIComponent(user.role || "")}`
    )
      .then((response) => {
        setMessages(response.messages || []);
      })
      .catch((error) => {
        console.error(error);
        setStatus("Failed to load messages.");
      });
  }

  useEffect(() => {
    loadMessages();
  }, [workspace, clientId, projectId, channel, user]);

  function sendMessage() {
    if (!clientId || !projectId || !user) return;

    const trimmed = messageText.trim();

    if (!trimmed) {
      setStatus("Please enter a message.");
      return;
    }

    const recipients =
      channel === "private"
        ? privateRecipients
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
        : [];

    if (channel === "private" && recipients.length === 0) {
      setStatus("Enter at least one private recipient username.");
      return;
    }

    apiPost("/api/messages/send", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      channel,
      sender_username: user.username,
      sender_display_name: user.display_name || user.username,
      sender_role: user.role,
      recipient_usernames: recipients,
      message: trimmed,
      parent_message_id: replyToMessage?.message_id || "",
      forwarded_from_message_id: "",
      forwarded_from_sender: "",
      forwarded_body: "",
      important,
      urgent,
    })
      .then((response) => {
        setStatus(response.status === "sent" ? "Message sent." : "Message sent.");
        setMessageText("");
        setReplyToMessage(null);
        setSelectedMessage(null);
        setImportant(false);
        setUrgent(false);
        loadMessages();
      })
      .catch((error) => {
        console.error(error);
        setStatus("Failed to send message.");
      });
  }

  function sendForwardMessage() {
    if (!clientId || !projectId || !user || !forwardMessage) return;

    const recipients =
      forwardChannel === "private"
        ? forwardRecipients
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
        : [];

    if (forwardChannel === "private" && recipients.length === 0) {
      setStatus("Enter at least one private recipient username.");
      return;
    }

    apiPost("/api/messages/send", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      channel: forwardChannel,
      sender_username: user.username,
      sender_display_name: user.display_name || user.username,
      sender_role: user.role,
      recipient_usernames: recipients,
      message: `Forwarded message:\n\n${forwardMessage.message}`,
      parent_message_id: "",
      forwarded_from_message_id: forwardMessage.message_id,
      forwarded_from_sender:
        forwardMessage.sender_display_name ||
        forwardMessage.sender_username,
      forwarded_body: forwardMessage.message,
    })
      .then(() => {
        setStatus("Message forwarded.");
        setForwardMessage(null);
        setForwardRecipients("");
        setSelectedMessage(null);
        loadMessages();
      })
      .catch((error) => {
        console.error(error);
        setStatus("Failed to forward message.");
      });
  }

  if (!clientId || !projectId) {
    return (
      <ContentCard title="Messaging">
        <p className="text-slate-400">
          Select a client and project to use messaging.
        </p>
      </ContentCard>
    );
  }

  return (
    <div className="space-y-6">
      <ContentCard title="Messaging">
        <div className="flex items-center justify-between gap-3 mb-6">
          <div className="flex flex-wrap gap-3">
            <Button
              variant={channel === "project" ? "primary" : "secondary"}
              onClick={() => setChannel("project")}
            >
              Project Team
            </Button>

            {canUseAdminChannel && (
              <Button
                variant={channel === "admin" ? "primary" : "secondary"}
                onClick={() => setChannel("admin")}
              >
                Admin Team
              </Button>
            )}

            <Button
              variant={channel === "private" ? "primary" : "secondary"}
              onClick={() => setChannel("private")}
            >
              Private
            </Button>
          </div>

          <Button
            variant="secondary"
            onClick={loadMessages}
          >
            Refresh
          </Button>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950 h-[52vh] overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <p className="text-slate-500 text-sm">
              No messages yet.
            </p>
          ) : (
            messages.map((item) => {
              const sender =
                item.sender_display_name ||
                item.sender_username ||
                "Unknown User";

              const isMine =
                item.sender_username === user?.username;

              return (
                <div
                  key={item.message_id}
                  className={
                    selectedMessage?.message_id === item.message_id
                      ? "max-w-3xl rounded-2xl bg-sky-950 border-2 border-sky-400 p-4"
                      : isMine
                        ? "ml-auto max-w-3xl rounded-2xl bg-sky-900/50 border border-sky-700 p-4"
                        : "max-w-3xl rounded-2xl bg-slate-900 border border-slate-800 p-4"
                  }
                >
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <p className="text-sm font-semibold text-white flex items-center gap-2">
                      {(item.important || item.urgent) && (
                        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-red-600 text-white font-bold">
                          !
                        </span>
                      )}

                      {sender}
                    </p>

                    <p className="text-xs text-slate-500">
                      {item.created_at
                        ? new Date(item.created_at).toLocaleString()
                        : ""}
                    </p>
                  </div>

                  {item.parent_message_id && (
                    <p className="text-[11px] text-sky-400 mb-2">
                      Reply in thread
                    </p>
                  )}

                  {item.forwarded_from_message_id && (
                    <div className="mb-3 rounded-xl border border-slate-700 bg-slate-950 p-3">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
                        Forwarded from {item.forwarded_from_sender || "Unknown User"}
                      </p>
                      <p className="text-xs text-slate-300 whitespace-pre-wrap">
                        {item.forwarded_body}
                      </p>
                    </div>
                  )}

                  {item.channel === "private" && (
                    <p className="text-[11px] text-slate-500 mb-2">
                      Private to:{" "}
                      {(item.recipient_usernames || []).join(", ")}
                    </p>
                  )}

                  <p className="text-sm text-slate-200 whitespace-pre-wrap leading-6">
                    {item.message}
                  </p>

                  <div className="mt-4 flex justify-end gap-2">
                    <Button
                      variant={
                        selectedMessage?.message_id === item.message_id
                          ? "primary"
                          : "secondary"
                      }
                      onClick={() => setSelectedMessage(item)}
                    >
                      Select Message
                    </Button>

                    <Button
                      variant="secondary"
                      onClick={() => {
                        setSelectedMessage(item);
                        setReplyToMessage(item);
                        setForwardMessage(null);
                        setMessageText("");
                      }}
                    >
                      Reply
                    </Button>

                    <Button
                      variant="secondary"
                      onClick={() => {
                        setSelectedMessage(item);
                        setForwardMessage(item);
                        setReplyToMessage(null);
                      }}
                    >
                      Forward
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="mt-5 space-y-3">
          {channel === "private" && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Private recipients, comma-separated usernames
              </label>

              <input
                value={privateRecipients}
                onChange={(event) =>
                  setPrivateRecipients(event.target.value)
                }
                placeholder="reviewer1, tl_user, admin_user"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-500"
              />
            </div>
          )}

          {replyToMessage && (
            <div className="rounded-xl border border-sky-700 bg-sky-950/50 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-sky-400">
                    Replying to{" "}
                    {replyToMessage.sender_display_name ||
                      replyToMessage.sender_username}
                  </p>
                  <p className="text-sm text-slate-300 line-clamp-2">
                    {replyToMessage.message}
                  </p>
                </div>

                <Button
                  variant="secondary"
                  onClick={() => setReplyToMessage(null)}
                >
                  Cancel Reply
                </Button>
              </div>
            </div>
          )}

          {canSendAlertMessage && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={important}
                  onChange={(event) => {
                    if (urgent) return;
                    setImportant(event.target.checked);
                  }}
                />
                <span>Important</span>
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-red-600 text-white font-bold">
                  !
                </span>
              </label>

              <label className="flex items-center gap-3 rounded-xl border border-red-700 bg-red-950/40 px-4 py-3 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={urgent}
                  onChange={(event) => {
                    setUrgent(event.target.checked);

                    if (event.target.checked) {
                      setImportant(true);
                    }
                  }}
                />
                <span>Urgent — requires confirmation</span>
              </label>
            </div>
          )}

          <textarea
            value={messageText}
            onChange={(event) => setMessageText(event.target.value)}
            placeholder={
              channel === "project"
                ? "Message the project review team..."
                : channel === "admin"
                  ? "Message the admin team..."
                  : "Write a private message..."
            }
            className="min-h-[110px] w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-500"
          />

          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-slate-400">
              {status}
            </p>

            <Button onClick={sendMessage}>
              Send Message
            </Button>
          </div>

          {forwardMessage && (
            <div className="mt-5 rounded-2xl border border-slate-700 bg-slate-950 p-4">
              <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                  <p className="text-sm font-semibold text-white">
                    Forward Selected Message
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    From{" "}
                    {forwardMessage.sender_display_name ||
                      forwardMessage.sender_username}
                  </p>
                </div>

                <Button
                  variant="secondary"
                  onClick={() => setForwardMessage(null)}
                >
                  Cancel
                </Button>
              </div>

              <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900 p-3">
                <p className="text-sm text-slate-300 whitespace-pre-wrap">
                  {forwardMessage.message}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Forward To
                  </label>

                  <select
                    value={forwardChannel}
                    onChange={(event) =>
                      setForwardChannel(event.target.value as Channel)
                    }
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-500"
                  >
                    <option value="project">Project Team</option>

                    {canUseAdminChannel && (
                      <option value="admin">Admin Team</option>
                    )}

                    <option value="private">Private</option>
                  </select>
                </div>

                {forwardChannel === "private" && (
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Private recipients, comma-separated usernames
                    </label>

                    <input
                      value={forwardRecipients}
                      onChange={(event) =>
                        setForwardRecipients(event.target.value)
                      }
                      placeholder="reviewer1, tl_user, admin_user"
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-500"
                    />
                  </div>
                )}
              </div>

              <div className="flex justify-end">
                <Button onClick={sendForwardMessage}>
                  Send Forward
                </Button>
              </div>
            </div>
          )}

        </div>
      </ContentCard>
    </div>
  );
}
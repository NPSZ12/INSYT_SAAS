"use client";

import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import TextArea from "../../components/TextArea";
import FormLabel from "../../components/FormLabel";

export default function MessagingPage() {
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");

  const messages = [
    {
      sender: "CDS Admin",
      time: "Today at 9:15 AM",
      message: "Please prioritize Batch 001 and flag any illegible handwriting.",
    },
    {
      sender: "QC Lead",
      time: "Yesterday at 4:40 PM",
      message: "Reminder: capture full SSNs only, no partial last-four values.",
    },
  ];

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Return to Projects and select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Messaging"
          subtitle={`Project communications for ${projectId.replaceAll("_", " ")}.`}
        />

        <div className="grid grid-cols-2 gap-6">
          <ContentCard title="Project Messages">
            <div className="space-y-4">
              {messages.map((message) => (
                <div
                  key={`${message.sender}-${message.time}`}
                  className="bg-slate-950 border border-slate-800 rounded-xl p-4"
                >
                  <div className="flex justify-between mb-2">
                    <p className="font-semibold text-white">
                      {message.sender}
                    </p>

                    <p className="text-xs text-slate-500">
                      {message.time}
                    </p>
                  </div>

                  <p className="text-slate-300">
                    {message.message}
                  </p>
                </div>
              ))}
            </div>
          </ContentCard>

          <ContentCard title="Send Message">
            <FormLabel>Subject</FormLabel>
            <div className="mb-4">
              <Input placeholder="Message subject" />
            </div>

            <FormLabel>Message</FormLabel>
            <div className="mb-6">
              <TextArea rows={6} placeholder="Type project message..." />
            </div>

            <Button fullWidth>
              Send Message
            </Button>
          </ContentCard>
        </div>
      </PageContainer>
    </AppShell>
  );
}
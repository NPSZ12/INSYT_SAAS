"use client";

import { Suspense, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import Input from "../../../components/Input";
import FormLabel from "../../../components/FormLabel";
import Select from "../../../components/Select";
import { apiPost } from "../../../lib/api";

function NewProjectPageContent() {
  const [workspace, setWorkspace] = useState("capture");
  const [projectName, setProjectName] = useState("");
  const [clientName, setClientName] = useState("");
  const [message, setMessage] = useState("");

  function createProject() {
    if (!projectName.trim()) {
      setMessage("Project name is required.");
      return;
    }

    apiPost(`/api/${workspace}/projects/create`, {
      project_name: projectName,
      client_name: clientName,
    })
      .then((response) => {
        setMessage(response.message || "Project created.");
        setProjectName("");
        setClientName("");
      })
      .catch(() => {
        setMessage("Project creation failed.");
      });
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="New Project"
          subtitle="Create a new Azure project folder for Capture, Summaries, or Discovery."
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Create Azure Project">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <FormLabel>Workspace</FormLabel>
              <Select value={workspace} onChange={setWorkspace}>
                <option value="capture">INSYT Capture</option>
                <option value="summaries">INSYT Summaries</option>
                <option value="discovery">INSYT Discovery</option>
              </Select>
            </div>

            <div>
              <FormLabel>Project Name</FormLabel>
              <Input
                value={projectName}
                onChange={setProjectName}
                placeholder="Example: Project_Merlin"
              />
            </div>

            <div>
              <FormLabel>Client Name</FormLabel>
              <Input
                value={clientName}
                onChange={setClientName}
                placeholder="Example: Alpine"
              />
            </div>

            <div className="md:col-span-3">
              <Button onClick={createProject}>
                Create Project Folder
              </Button>
            </div>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}


export default function NewProjectPage() {
  return (
    <Suspense fallback={<div>Loading new project...</div>}>
      <NewProjectPageContent />
    </Suspense>
  );
}






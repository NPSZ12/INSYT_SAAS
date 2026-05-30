"use client";

import { useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import FormLabel from "../../components/FormLabel";
import Select from "../../components/Select";
import { apiGet, apiPost } from "../../lib/api";

export default function NewProjectPage() {
  const [workspace, setWorkspace] = useState("capture");
  const [projectName, setProjectName] = useState("");
  const [clients, setClients] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState("");
  const [newClientName, setNewClientName] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    apiGet(`/api/${workspace}/clients`)
      .then((response) => {
        setClients(response.clients || []);
      })
      .catch(() => {
        setClients([]);
      });
  }, [workspace]);

  function createProject() {
    const client = selectedClient || newClientName;

    if (!client.trim()) {
      setMessage("Client name is required.");
      return;
    }

    if (!projectName.trim()) {
      setMessage("Project name is required.");
      return;
    }

    apiPost(`/api/${workspace}/projects/create`, {
      project_id: projectName,
      client,
    })
      .then(() => {
        setMessage(
          `Created ${client}/${projectName} in ${workspace}.`
        );

        setProjectName("");
        setSelectedClient("");
        setNewClientName("");

        return apiGet(`/api/${workspace}/clients`);
      })
      .then((response) => {
        setClients(response.clients || []);
      })
      .catch(() => {
        setMessage("Project creation failed.");
      });
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Project Management"
          subtitle="Create and manage client projects, workspace folders, and project protocols."
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Create Azure Project">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <FormLabel>Workspace</FormLabel>

              <Select
                value={workspace}
                onChange={(value) => {
                  setWorkspace(value);
                  setSelectedClient("");
                  setNewClientName("");
                }}
              >
                <option value="capture">INSYT Capture</option>
                <option value="summaries">INSYT Summaries</option>
                <option value="discovery">INSYT Discovery</option>
              </Select>
            </div>

            <div>
              <FormLabel>Existing Client</FormLabel>

              <Select
                value={selectedClient}
                onChange={(value) => {
                  setSelectedClient(value);

                  if (value) {
                    setNewClientName("");
                  }
                }}
              >
                <option value="">
                  Select existing client...
                </option>

                {clients.map((client) => (
                  <option key={client} value={client}>
                    {client.replaceAll("_", " ")}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <FormLabel>Or Create New Client</FormLabel>

              <Input
                value={newClientName}
                onChange={(value) => {
                  setNewClientName(value);

                  if (value) {
                    setSelectedClient("");
                  }
                }}
                placeholder="Example: NLCP"
              />
            </div>

            <div>
              <FormLabel>Project Name</FormLabel>

              <Input
                value={projectName}
                onChange={setProjectName}
                placeholder="Example: Project_NLCP-POC"
              />
            </div>

            <div className="md:col-span-4">
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
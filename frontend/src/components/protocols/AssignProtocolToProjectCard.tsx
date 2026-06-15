"use client";

import { useEffect, useMemo, useState } from "react";

import ContentCard from "../ContentCard";
import FormLabel from "../FormLabel";
import Select from "../Select";
import Button from "../Button";

import { apiGet, apiPost } from "../../lib/api";

type Workspace = "capture" | "discovery" | "summaries";

type AssignProtocolToProjectCardProps = {
  defaultWorkspace: Workspace;
};

type ProtocolOption = {
  name: string;
  fields: Record<string, any>[];
};

const WORKSPACE_LABELS: Record<Workspace, string> = {
  capture: "INSYT Capture",
  discovery: "INSYT Discovery",
  summaries: "INSYT Summaries",
};

function normalizeProtocolOptions(response: any): ProtocolOption[] {
  const templates =
    response?.protocols ||
    response?.templates ||
    response?.items ||
    [];

  if (Array.isArray(templates)) {
    return templates
      .map((item: any) => {
        if (typeof item === "string") {
          return {
            name: item,
            fields: [],
          };
        }

        const name =
          item?.name ||
          item?.protocol_name ||
          item?.protocol_template ||
          item?.template_name ||
          "";

        return {
          name: String(name || "").trim(),
          fields: Array.isArray(item?.fields) ? item.fields : [],
        };
      })
      .filter((item) => item.name);
  }

  if (response?.templates && typeof response.templates === "object") {
    return Object.entries(response.templates).map(([name, fields]) => ({
      name,
      fields: Array.isArray(fields) ? fields : [],
    }));
  }

  return [];
}

export default function AssignProtocolToProjectCard({
  defaultWorkspace,
}: AssignProtocolToProjectCardProps) {
  const [selectedWorkspace, setSelectedWorkspace] =
    useState<Workspace>(defaultWorkspace);

  const [clients, setClients] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [protocols, setProtocols] = useState<ProtocolOption[]>([]);

  const [selectedClient, setSelectedClient] = useState("");
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedProtocol, setSelectedProtocol] = useState("");

  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");

  const selectedProtocolOption = useMemo(
    () => protocols.find((protocol) => protocol.name === selectedProtocol),
    [protocols, selectedProtocol]
  );

  useEffect(() => {
    setSelectedClient("");
    setSelectedProject("");
    setSelectedProtocol("");
    setClients([]);
    setProjects([]);
    setProtocols([]);
    setStatusMessage("");
    setError("");

    apiGet(`/api/${selectedWorkspace}/clients`)
      .then((response: any) => {
        setClients(response.clients || response || []);
      })
      .catch((error: any) => {
        console.error(error);
        setError("Failed to load clients.");
      });

    apiGet(`/api/${selectedWorkspace}/protocol-templates`)
      .then((response: any) => {
        setProtocols(normalizeProtocolOptions(response));
      })
      .catch((error: any) => {
        console.error(error);
        setError("Failed to load protocol templates.");
      });
  }, [selectedWorkspace]);

  useEffect(() => {
    if (!selectedClient) {
      setProjects([]);
      setSelectedProject("");
      return;
    }

    setProjects([]);
    setSelectedProject("");
    setStatusMessage("");
    setError("");

    apiGet(
      `/api/${selectedWorkspace}/clients/${encodeURIComponent(
        selectedClient
      )}/projects`
    )
      .then((response: any) => {
        setProjects(response.projects || response || []);
      })
      .catch((error: any) => {
        console.error(error);
        setError("Failed to load projects.");
      });
  }, [selectedWorkspace, selectedClient]);

  async function loadProtocolFieldsIfNeeded(
    protocolName: string,
    existingFields: Record<string, any>[]
  ) {
    if (existingFields.length > 0) {
      return existingFields;
    }

    const encodedProtocol = encodeURIComponent(protocolName);

    const possibleUrls = [
      `/api/${selectedWorkspace}/protocol-templates/${encodedProtocol}`,
      `/api/${selectedWorkspace}/protocol-templates/${encodedProtocol}/fields`,
    ];

    for (const url of possibleUrls) {
      try {
        const response = (await apiGet(url)) as any;

        const fields =
          response?.fields ||
          response?.protocol?.fields ||
          response?.template?.fields ||
          [];

        if (Array.isArray(fields)) {
          return fields;
        }
      } catch {
        // Try next candidate endpoint.
      }
    }

    return [];
  }

  async function assignProtocol() {
    setStatusMessage("");
    setError("");

    if (
      !selectedWorkspace ||
      !selectedClient ||
      !selectedProject ||
      !selectedProtocol
    ) {
      setError("Select workspace, client, project, and protocol first.");
      return;
    }

    try {
      const fields = await loadProtocolFieldsIfNeeded(
        selectedProtocol,
        selectedProtocolOption?.fields || []
      );

      const protocolUrl =
        `/api/${selectedWorkspace}/projects/${encodeURIComponent(
          selectedProject
        )}/protocol` +
        `?client=${encodeURIComponent(selectedClient)}`;

      await apiPost(protocolUrl, {
        client: selectedClient,
        protocol_template: selectedProtocol,
        fields,
        override: true,
      });

      setStatusMessage(
        `Protocol assigned to ${selectedClient}/${selectedWorkspace}/${selectedProject}.`
      );
    } catch (error: any) {
      console.error(error);
      setError(
        String(error?.message || "Failed to assign protocol to project.")
      );
    }
  }

  return (
    <ContentCard title="Assign Protocol to Project">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <FormLabel>Select Workspace</FormLabel>

          <Select
            value={selectedWorkspace}
            onChange={(value) => setSelectedWorkspace(value as Workspace)}
          >
            {Object.entries(WORKSPACE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <FormLabel>Select Client</FormLabel>

          <Select value={selectedClient} onChange={setSelectedClient}>
            <option value="">Select client...</option>

            {clients.map((client) => (
              <option key={client} value={client}>
                {client.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <FormLabel>Select Project</FormLabel>

          <Select value={selectedProject} onChange={setSelectedProject}>
            <option value="">Select project...</option>

            {projects.map((project) => (
              <option key={project} value={project}>
                {project.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <FormLabel>Select Protocol</FormLabel>

          <Select value={selectedProtocol} onChange={setSelectedProtocol}>
            <option value="">Select protocol...</option>

            {protocols.map((protocol) => (
              <option key={protocol.name} value={protocol.name}>
                {protocol.name.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="mt-5 flex items-center gap-4">
        <Button onClick={assignProtocol}>
          Assign Protocol
        </Button>

        {statusMessage && (
          <p className="text-sm text-emerald-400">
            {statusMessage}
          </p>
        )}

        {error && (
          <p className="text-sm text-red-400">
            {error}
          </p>
        )}
      </div>
    </ContentCard>
  );
}
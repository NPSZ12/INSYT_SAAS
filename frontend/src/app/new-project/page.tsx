"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import FormLabel from "../../components/FormLabel";
import Select from "../../components/Select";
import { apiGet, apiPost } from "../../lib/api";
import ProjectFileUploadCard from "../../components/ProjectFileUploadCard";


type ProtocolTemplateField = {
  section: string;
  data_element: string;
  default_format: string;
  notes: string;
};

type RegistryClient = {
  client_uuid: string;
  client_name: string;
  normalized_name?: string;
  workspaces?: string[];
};

export default function NewProjectPage() {
  const [workspace, setWorkspace] = useState("capture");
  const [projectName, setProjectName] = useState("");
  const [clients, setClients] = useState<string[]>([]);
  const [registryClients, setRegistryClients] = useState<RegistryClient[]>([]);
  const [selectedClient, setSelectedClient] = useState("");
  const [selectedClientUuid, setSelectedClientUuid] = useState("");
  const [newClientName, setNewClientName] = useState("");
  const [message, setMessage] = useState("");

  const [projects, setProjects] = useState<string[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [protocolTemplates, setProtocolTemplates] = useState<
    Record<string, ProtocolTemplateField[]>
  >({});
  const [fieldSelections, setFieldSelections] = useState<
    Record<string, "Text Capture" | "Tag" | "">
  >({});
  const [customFields, setCustomFields] = useState<
    Record<string, ProtocolTemplateField[]>
  >({});

  const [overlayView, setOverlayView] =
    useState<"raw" | "final">("raw");

  function loadRegistryClients() {
    apiGet("/api/workspace-registry/clients")
      .then((response) => {
        setRegistryClients(response.clients || []);
      })
      .catch((error) => {
        console.error("Failed to load registered clients:", error);
        setRegistryClients([]);
      });
  }

  function loadProjects(clientOverride?: string) {
    const client = clientOverride ?? selectedClient;

    if (!client) {
      setProjects([]);
      setSelectedProject("");
      return;
    }

    const endpoint =
      `/api/${workspace}/clients/${encodeURIComponent(client)}/projects`;

    apiGet(endpoint)
      .then((response) => {
        if (Array.isArray(response)) {
          setProjects(response);
          return;
        }

        if (Array.isArray(response.projects)) {
          setProjects(response.projects);
          return;
        }

        console.error("Unexpected projects response:", response);
        setProjects([]);
        setMessage("Unable to load projects.");
      })
      .catch((error) => {
        console.error("Failed to load projects:", error);
        setProjects([]);
        setMessage("Failed to load available projects.");
      });
  }

  function loadProtocolTemplates() {
    apiGet(`/api/${workspace}/protocol-templates`)
      .then((response) => {
        setProtocolTemplates(response.templates || {})
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load protocol templates.");
      });
  }

  useEffect(() => {
    loadRegistryClients();
  }, []);

  useEffect(() => {
    apiGet(`/api/${workspace}/clients`)
      .then((response) => {
        const loadedClients = response.clients || [];

        setClients(loadedClients);

        if (
          selectedClient &&
          !loadedClients.includes(selectedClient)
        ) {
          setSelectedClient("");
          setSelectedProject("");
        }
      })
      .catch(() => {
        setClients([]);
        setSelectedClient("");
        setSelectedProject("");
      });

    setSelectedTemplate("");
    setFieldSelections({});
    loadProtocolTemplates();
  }, [workspace]);

  useEffect(() => {
    if (!selectedClient) {
      setProjects([]);
      setSelectedProject("");
      return;
    }

    loadProjects();
  }, [workspace, selectedClient]);

  function createProject() {
    const selectedRegistryClient = registryClients.find(
      (client) => client.client_uuid === selectedClientUuid
    );

    const clientName =
      selectedRegistryClient?.client_name ||
      newClientName;

    if (!clientName.trim()) {
      setMessage("Client name is required.");
      return;
    }

    if (!projectName.trim()) {
      setMessage("Project name is required.");
      return;
    }

    apiPost("/api/workspace-registry/projects/create", {
      client_uuid: selectedRegistryClient?.client_uuid || "",
      client_name: clientName,
      workspace,
      project_name: projectName,
    })
      .then((response) => {
        setMessage(
          `Created ${response.client}/${response.project} in ${response.workspace}. Client UUID: ${response.client_uuid}. Project UUID: ${response.project_uuid}.`
        );

        setProjectName("");
        setNewClientName("");
        setSelectedClientUuid(response.client_uuid || "");
        setSelectedClient(response.client || clientName);

        loadRegistryClients();
        loadProjects(response.client || clientName);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Project creation failed.");
      });
  }

  function normalizeDefaultFormat(value: string) {
    const normalized = value.trim().toLowerCase();

    if (
      normalized === "text capture" ||
      normalized === "text" ||
      normalized === "capture"
    ) {
      return "Text Capture";
    }

    if (
      normalized === "tag" ||
      normalized === "add-tag" ||
      normalized === "add tag" ||
      normalized === "entity tag"
    ) {
      return "Tag";
    }

    return "";
  }

  function selectTemplate(templateName: string) {
    setSelectedTemplate(templateName);

    const defaults: Record<string, "Text Capture" | "Tag" | ""> = {};

    (protocolTemplates[templateName] || []).forEach((field) => {
      const key = `${templateName}::${field.data_element}`;

      defaults[key] = normalizeDefaultFormat(
        field.default_format || ""
      ) as "Text Capture" | "Tag" | "";
    });

    setFieldSelections(defaults);
  }

  function updateFieldSelection(
    key: string,
    value: "Text Capture" | "Tag" | ""
  ) {
    setFieldSelections((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function addNewDataElement() {
    if (!selectedTemplate) return;

    const name = window.prompt("Enter new data element name:");

    if (!name?.trim()) return;

    const newField: ProtocolTemplateField = {
      section: "Custom",
      data_element: name.trim(),
      default_format: "",
      notes: "Custom project-specific data element",
    };

    setCustomFields((current) => ({
      ...current,
      [selectedTemplate]: [
        ...(current[selectedTemplate] || []),
        newField,
      ],
    }));

    const key = `${selectedTemplate}::${newField.data_element}`;
    updateFieldSelection(key, "Text Capture");
  }

  function buildProtocolFields() {
    return selectedFields
      .filter((field) => {
        const key = `${selectedTemplate}::${field.data_element}`;
        const currentValue =
          fieldSelections[key] ||
          normalizeDefaultFormat(field.default_format || "");

        return currentValue;
      })
      .map((field) => {
        const key = `${selectedTemplate}::${field.data_element}`;
        const currentValue =
          fieldSelections[key] ||
          normalizeDefaultFormat(field.default_format || "");

        return {
          section: field.section || selectedTemplate,
          data_element: field.data_element,
          format: currentValue || "Text Capture",
          notes: field.notes || "",
        };
      });
  }

  function saveProtocol() {
    if (!selectedProject) {
      setMessage("Select a project before saving a protocol.");
      return;
    }

    if (!selectedTemplate) {
      setMessage("Select a protocol template first.");
      return;
    }

    apiPost(`/api/${workspace}/projects/${selectedProject}/protocol`, {
      protocol_template: selectedTemplate,
      fields: buildProtocolFields(),
      override: false,
    })
      .then((response) => {
        console.log("PROTOCOL SAVE RESPONSE", response);

        setMessage(
          `Protocol saved to: ${
            response.protocol_blob || "unknown location"
          }`
        );
      })
      .catch((error) => {
        const text = String(error?.message || "");

        if (text.includes("409")) {
          const user = JSON.parse(
            localStorage.getItem("insyt_user") || "{}"
          );

          const role =
            user?.role ||
            user?.user_role ||
            user?.access_level ||
            "";

          const isAdmin =
            String(role).toLowerCase().includes("admin");

          if (!isAdmin) {
            setMessage(
              "Protocol already selected. INSYT Admin approval is required to override."
            );
            return;
          }

          const confirmed = window.confirm(
            "A protocol already exists for this project.\n\nDo you want to override the existing protocol?"
          );

          if (!confirmed) {
            setMessage("Protocol override cancelled.");
            return;
          }

          apiPost(`/api/${workspace}/projects/${selectedProject}/protocol`, {
            protocol_template: selectedTemplate,
            fields: buildProtocolFields(),
            override: true,
          })
            .then((response) => {
              setMessage(response.message || "Protocol overridden.");
            })
            .catch((overrideError) => {
              console.error(overrideError);
              setMessage("Protocol override failed.");
            });

          return;
        }

        console.error(error);
        setMessage("Failed to save protocol.");
      });
  }

  const selectedFields =
    selectedTemplate
      ? [
          ...(protocolTemplates[selectedTemplate] || []),
          ...(customFields[selectedTemplate] || []),
        ]
      : [];

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
              <FormLabel>Target Workspace</FormLabel>

              <Select value={workspace} onChange={setWorkspace}>
                <option value="capture">INSYT Capture</option>
                <option value="summaries">INSYT Summaries</option>
                <option value="discovery">INSYT Discovery</option>
              </Select>
            </div>

            <div>
              <FormLabel>Existing Client</FormLabel>

              <Select
                value={selectedClientUuid}
                onChange={(value) => {
                  setSelectedClientUuid(value);

                  const selected = registryClients.find(
                    (client) => client.client_uuid === value
                  );

                  if (selected) {
                    setSelectedClient(selected.client_name);
                    setNewClientName("");
                  } else {
                    setSelectedClient("");
                  }
                }}
              >
                <option value="">Select existing client...</option>

                {registryClients.map((client) => (
                  <option key={client.client_uuid} value={client.client_uuid}>
                    {client.client_name.replaceAll("_", " ")}
                    {client.workspaces?.length
                      ? ` (${client.workspaces.join(", ")})`
                      : ""}
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
                    setSelectedClientUuid("");
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
                placeholder="Example: Project_Merlin"
              />
            </div>

            <div className="md:col-span-3">
              <Button onClick={createProject}>
                Create Project Folder
              </Button>
            </div>
          </div>
        </ContentCard>

        <div className="mt-8">
          <ProjectFileUploadCard
            projects={projects}
            selectedProject={selectedProject}
            setSelectedProject={setSelectedProject}
            setMessage={setMessage}
          />
        </div>

        <div className="mt-8">
          <ContentCard title="Assign Protocol to Project">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end mb-6">
              <div>
                <FormLabel>Select Workspace</FormLabel>

                <Select value={workspace} onChange={setWorkspace}>
                  <option value="capture">INSYT Capture</option>
                  <option value="discovery">INSYT Discovery</option>
                  <option value="summaries">INSYT Summaries</option>
                </Select>
              </div>

              <div>
                <FormLabel>Select Client</FormLabel>

                <Select
                  value={selectedClient}
                  onChange={(value) => {
                    setSelectedClient(value);
                    setSelectedProject("");
                  }}
                >
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

                <Select
                  value={selectedProject}
                  onChange={setSelectedProject}
                >
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

                <Select
                  value={selectedTemplate}
                  onChange={selectTemplate}
                >
                  <option value="">Select protocol...</option>

                  {Object.keys(protocolTemplates).map((template) => (
                    <option key={template} value={template}>
                      {template}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            {selectedTemplate && (
              <div className="border border-slate-800 rounded-xl overflow-hidden">
                <div className="bg-slate-950 px-4 py-3 border-b border-slate-800">
                  <h3 className="insyt-workspace text-lg font-semibold text-white">
                    {selectedTemplate} Data Elements
                  </h3>

                  <p className="text-xs text-slate-500 mt-1">
                    Defaults are loaded from Column C of the protocol workbook.
                  </p>
                </div>

                <div className="max-h-[62vh] overflow-auto">
                  <table className="w-full text-xs table-auto">
                    <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                      <tr>
                        <th className="p-3 text-left">Section</th>
                        <th className="p-3 text-left">Data Element</th>
                        <th className="p-3 text-left">Notes</th>
                        <th className="p-3 text-left">Capture Type</th>
                      </tr>
                    </thead>

                    <tbody>
                      {selectedFields.map((field) => {
                        const key = `${selectedTemplate}::${field.data_element}`;

                        const currentValue =
                          fieldSelections[key] ||
                          normalizeDefaultFormat(field.default_format || "");

                        return (

                          <tr
                            key={key}
                            className="border-t border-slate-800 align-top"
                          >
                            <td className="p-3 text-slate-300">
                              {field.section || "—"}
                            </td>

                            <td className="p-3 text-white">
                              {field.data_element}
                            </td>

                            <td className="p-3 text-slate-400">
                              {field.notes || "—"}
                            </td>

                            <td className="p-3">
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  onClick={() =>
                                    updateFieldSelection(
                                      key,
                                      "Text Capture"
                                    )
                                  }
                                  className={
                                    currentValue === "Text Capture"
                                      ? normalizeDefaultFormat(field.default_format || "") === "Text Capture"
                                        ? "bg-sky-100 text-sky-800 border border-sky-400 font-semibold px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                        : "bg-lime-50 text-slate-950 px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                      : "bg-slate-800 text-slate-300 px-3 py-2 rounded-lg hover:bg-slate-700 whitespace-nowrap flex items-center"
                                  }
                                >
                                  Text Capture

                                  {normalizeDefaultFormat(field.default_format || "") === "Text Capture" && (
                                    <span className="ml-2 text-[10px] bg-sky-400 text-white px-2 py-0.5 rounded-full">
                                      Standard
                                    </span>
                                  )}
                                </button>

                                <button
                                  type="button"
                                  onClick={() =>
                                    updateFieldSelection(
                                      key,
                                      "Tag"
                                    )
                                  }
                                  className={
                                    currentValue === "Tag"
                                      ? normalizeDefaultFormat(field.default_format || "") === "Tag"
                                        ? "bg-violet-100 text-violet-800 border border-violet-400 font-semibold px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                        : "bg-lime-50 text-slate-950 px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                      : "bg-slate-800 text-slate-300 px-3 py-2 rounded-lg hover:bg-slate-700 whitespace-nowrap flex items-center"
                                  }
                                >
                                  Tag

                                  {normalizeDefaultFormat(field.default_format || "") === "Tag" && (
                                    <span className="ml-2 text-[10px] bg-violet-700 text-white px-2 py-0.5 rounded-full">
                                      Standard
                                    </span>
                                  )}
                                </button>

                                <button
                                  type="button"
                                  onClick={() =>
                                    updateFieldSelection(key, "")
                                  }
                                  className={
                                    currentValue === ""
                                      ? "bg-slate-600 text-white px-3 py-2 rounded-lg whitespace-nowrap"
                                      : "bg-slate-800 text-slate-300 px-3 py-2 rounded-lg hover:bg-slate-700 whitespace-nowrap"
                                  }
                                >
                                  Exclude
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="p-4 border-t border-slate-800 bg-slate-950 flex justify-between items-center">
                  <p className="text-sm text-slate-400">
                    {buildProtocolFields().length} selected field(s)
                  </p>

                  <div className="flex gap-3">
                    <Button
                      variant="secondary"
                      onClick={addNewDataElement}
                    >
                      Add New Data Element
                    </Button>

                    <Button onClick={saveProtocol}>
                      Save Protocol to Project
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </ContentCard>
        </div>
        
        <div className="mt-8">
          <ContentCard title="Overlay Upload">
            <div className="space-y-4">
              <p className="text-sm text-slate-400">
                Upload CSV, JSON, or DAT overlays into Raw or Final overlay storage.
                Uploaded headers must exactly match the saved project protocol and
                include a Doc ID column.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <FormLabel>Workspace</FormLabel>

                  <Select
                    value={workspace}
                    onChange={(value) => {
                      setWorkspace(value);
                      setSelectedClient("");
                      setSelectedProject("");
                      setProjects([]);
                    }}
                  >
                    <option value="capture">Capture</option>
                    <option value="discovery">Discovery</option>
                    <option value="summaries">Summaries</option>
                  </Select>
                </div>

                <div>
                  <FormLabel>Client</FormLabel>

                  <Select
                    value={selectedClient}
                    onChange={(value) => {
                      setSelectedClient(value);
                      setSelectedProject("");
                    }}
                  >
                    <option value="">Select client...</option>

                    {clients.map((client) => (
                      <option key={client} value={client}>
                        {client}
                      </option>
                    ))}
                  </Select>
                </div>

                <div>
                  <FormLabel>Project</FormLabel>

                  <Select
                    value={selectedProject}
                    onChange={setSelectedProject}
                  >
                    <option value="">Select project...</option>

                    {projects.map((project) => (
                      <option key={project} value={project}>
                        {project.replaceAll("_", " ")}
                      </option>
                    ))}
                  </Select>
                </div>

                <div>
                  <FormLabel>Overlay Target</FormLabel>

                  <Select
                    value={overlayView}
                    onChange={(value) =>
                      setOverlayView(value as "raw" | "final")
                    }
                  >
                    <option value="raw">Raw</option>
                    <option value="final">Final</option>
                  </Select>
                </div>
              </div>

              <Button
                variant="secondary"
                onClick={() => {
                  if (!selectedClient) {
                    setMessage("Select a client before opening Overlay Upload.");
                    return;
                  }

                  if (!selectedProject) {
                    setMessage("Select a project before opening Overlay Upload.");
                    return;
                  }

                  const params = new URLSearchParams({
                    workspace,
                    client: selectedClient,
                    project: selectedProject,
                    overlay_view: overlayView,
                  });

                  window.location.href = `/project-management/upload-overlay?${params.toString()}`;
                }}
              >
                Open Overlay Upload
              </Button>
            </div>
          </ContentCard>
        </div>

      </PageContainer>
    </AppShell>
  );
}










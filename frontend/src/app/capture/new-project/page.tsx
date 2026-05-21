"use client";

import { useEffect, useState } from "react";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import Input from "../../../components/Input";
import FormLabel from "../../../components/FormLabel";
import Select from "../../../components/Select";
import { apiGet, apiPost } from "../../../lib/api";

type ProtocolTemplateField = {
  section: string;
  data_element: string;
  default_format: string;
  notes: string;
};

export default function NewProjectPage() {
  const [workspace, setWorkspace] = useState("capture");
  const [projectName, setProjectName] = useState("");
  const [clientName, setClientName] = useState("");
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

  function loadProjects() {
    const endpoint =
      workspace === "capture"
        ? "/api/azure-projects/"
        : `/api/${workspace}/projects`;

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
        setProtocolTemplates(response.templates || [])
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load protocol templates.");
      });
  }

  useEffect(() => {
    loadProjects();
    loadProtocolTemplates();
  }, [workspace]);

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
        loadProjects();
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
    setFieldSelections({});
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
        return fieldSelections[key];
      })
      .map((field) => {
        const key = `${selectedTemplate}::${field.data_element}`;

        return {
          section: field.section || selectedTemplate,
          data_element: field.data_element,
          format: fieldSelections[key] || field.default_format || "Text Capture",
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
        setMessage(response.message || "Protocol saved.");
      })
      .catch((error) => {
        const text = String(error?.message || "");

        if (text.includes("409")) {
          setMessage(
            "Protocol already selected. INSYT Admin approval is required to override."
          );
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
          title="New Project"
          subtitle="Create Azure projects and assign project-specific protocols."
        />

        {message && (
          <p className="text-sm text-sky-700 mb-6">
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

        <div className="mt-8">
          <ContentCard title="Upload Files to Project">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
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

              <div className="md:col-span-2">
                <FormLabel>Select Files</FormLabel>

                <input
                  type="file"
                  multiple
                  className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-lg file:border-0 file:bg-teal-500 file:px-4 file:py-2 file:text-slate hover:file:bg-sky-500"
                  onChange={(event) => {
                    const files = event.target.files;

                    if (!files || files.length === 0) {
                      setMessage("No files selected.");
                      return;
                    }

                    setMessage(
                      `${files.length} file(s) selected. Upload endpoint will be connected next.`
                    );
                  }}
                />
              </div>

              <div className="md:col-span-3">
                <Button
                  variant="secondary"
                  onClick={() => {
                    if (!selectedProject) {
                      setMessage("Select a project before uploading files.");
                      return;
                    }

                    setMessage(
                      "Upload Files to Project backend connection is next."
                    );
                  }}
                >
                  Upload Files to Project
                </Button>
              </div>
            </div>
          </ContentCard>
        </div>

        <div className="mt-8">
          <ContentCard title="Assign Protocol to Project">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end mb-6">
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
                                    fieldSelections[key] === "Text Capture"
                                      ? normalizeDefaultFormat(field.default_format || "") === "Text Capture"
                                        ? "bg-sky-100 text-sky-800 border border-sky-400 font-semibold px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                        : "bg-teal-500 text-slate-950 px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                      : "bg-slate-800 text-slate-300 px-3 py-2 rounded-lg hover:bg-slate-700 whitespace-nowrap flex items-center"
                                  }
                                >
                                  Text Capture

                                  {normalizeDefaultFormat(field.default_format || "") === "Text Capture" && (
                                    <span className="ml-2 text-[10px] bg-sky-700 text-white px-2 py-0.5 rounded-full">
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
                                    fieldSelections[key] === "Tag"
                                      ? normalizeDefaultFormat(field.default_format || "") === "Tag"
                                        ? "bg-violet-100 text-violet-800 border border-violet-400 font-semibold px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
                                        : "bg-teal-500 text-slate-950 px-3 py-2 rounded-lg whitespace-nowrap flex items-center"
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
                                    fieldSelections[key] === ""
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
      </PageContainer>
    </AppShell>
  );
}










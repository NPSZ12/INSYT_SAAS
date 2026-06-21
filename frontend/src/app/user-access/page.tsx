"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import Select from "../../components/Select";
import FormLabel from "../../components/FormLabel";
import Checkbox from "../../components/Checkbox";
import { apiGet, apiPost } from "../../lib/api";

type AccessUser = {
  username: string;
  display_name: string;
  email?: string;
  role: string;
  status: string;
  workspace_access?: string[];
  client_access?: string[];
  project_access?: string[];
  permissions?: string[];
  auth_provider?: string;
};

type UserAccessForm = {
  display_name: string;
  email: string;
  username: string;
  password: string;
  role: string;
  workspace_access: string[];
  client_access: string[];
  project_access: string[];
  permissions: string[];
  auth_provider: string;
};

const levels = [
  "1L",
  "QC",
  "TL",
  "RM",
  "Admin",
  "INSYT Admin",
  "Client",
];

const workspaces = [
  { value: "capture", label: "INSYT Capture" },
  { value: "discovery", label: "INSYT Discovery" },
  { value: "summaries", label: "INSYT Summaries" },
];

type WorkspaceTree = Record<string, string[]>;

type AccessTree = Record<string, WorkspaceTree>;

function makeClientAccessKey(workspace: string, client: string) {
  return `${workspace}/${client}`;
}

function makeProjectAccessKey(
  workspace: string,
  client: string,
  project: string
) {
  return `${workspace}/${client}/${project}`;
}

function parseClientAccessKey(value: string) {
  const parts = value.split("/");

  if (parts.length >= 2) {
    return {
      workspace: parts[0],
      client: parts.slice(1).join("/"),
    };
  }

  return {
    workspace: "",
    client: value,
  };
}

function parseProjectAccessKey(value: string) {
  const parts = value.split("/");

  if (parts.length >= 3) {
    return {
      workspace: parts[0],
      client: parts[1],
      project: parts.slice(2).join("/"),
    };
  }

  if (parts.length === 2) {
    return {
      workspace: "",
      client: parts[0],
      project: parts[1],
    };
  }

  return {
    workspace: "",
    client: "",
    project: value,
  };
}

const permissions = [
  "Download Docs",
  "Upload Docs",
  "Edit Summaries",
  "Delete Summaries",
  "Create Batches",
  "Create Search Folders",
  "View Messaging",
  "Send Messaging",
];

function makeEmptyForm(defaultWorkspace = "summaries"): UserAccessForm {
  return {
    display_name: "",
    email: "",
    username: "",
    password: "",
    role: "1L",
    workspace_access: [defaultWorkspace],
    client_access: [],
    project_access: [],
    permissions: [],
    auth_provider: "entra",
  };
}

function UserAccessPageContent() {
  const searchParams = useSearchParams();

  const defaultWorkspace =
    searchParams.get("workspace") || "summaries";

  const [users, setUsers] = useState<AccessUser[]>([]);
  const [accessTree, setAccessTree] = useState<AccessTree>({});
  const [expandedWorkspaces, setExpandedWorkspaces] =
    useState<Record<string, boolean>>({});
  const [expandedClients, setExpandedClients] =
    useState<Record<string, boolean>>({});
  const [permissionsExpanded, setPermissionsExpanded] =
    useState(false);

  const [selectedUsers, setSelectedUsers] =
    useState<Record<string, boolean>>({});

  const [message, setMessage] = useState("");
  const [showUserWarningModal, setShowUserWarningModal] =
    useState(false);
  const [userWarningTitle, setUserWarningTitle] = useState("");
  const [userWarningMessage, setUserWarningMessage] = useState("");

  const [form, setForm] = useState<UserAccessForm>(
    makeEmptyForm(defaultWorkspace)
  );

  const isInsytAdminLevel =
    form.role === "INSYT Admin";

  function resetForm() {
    setForm(makeEmptyForm(defaultWorkspace));
    setSelectedUsers({});
  }

  function loadUsers() {
    apiGet("/api/users/")
      .then((response: any) => {
        setUsers(
          Array.isArray(response)
            ? response
            : response?.users || []
        );
      })
      .catch(console.error);
  }

  async function loadAccessTree() {
    const nextTree: AccessTree = {};

    await Promise.all(
      workspaces.map(async (workspace) => {
        try {
          const clientsResponse: any = await apiGet(
            `/api/${workspace.value}/clients`
          );

          const workspaceClients: string[] =
            clientsResponse.clients || [];

          nextTree[workspace.value] = {};

          await Promise.all(
            workspaceClients.map(async (client) => {
              try {
                const projectsResponse: any = await apiGet(
                  `/api/${workspace.value}/clients/${encodeURIComponent(
                    client
                  )}/projects`
                );

                nextTree[workspace.value][client] =
                  projectsResponse.projects || [];
              } catch (error) {
                console.error(error);
                nextTree[workspace.value][client] = [];
              }
            })
          );
        } catch (error) {
          console.error(error);
          nextTree[workspace.value] = {};
        }
      })
    );

    setAccessTree(nextTree);
  }

  useEffect(() => {
    loadUsers();
  }, []);

  useEffect(() => {
    loadAccessTree();
  }, []);


  function toggleArrayValue(
    key: "client_access" | "project_access" | "permissions",
    value: string
  ) {
    setForm((current) => {
      const exists = current[key].includes(value);

      return {
        ...current,
        [key]: exists
          ? current[key].filter((item) => item !== value)
          : [...current[key], value],
      };
    });
  }

  function toggleExpandedWorkspace(workspace: string) {
    setExpandedWorkspaces((current) => ({
      ...current,
      [workspace]: !current[workspace],
    }));
  }

  function toggleExpandedClient(workspace: string, client: string) {
    const clientKey = makeClientAccessKey(workspace, client);

    setExpandedClients((current) => ({
      ...current,
      [clientKey]: !current[clientKey],
    }));
  }

  function getWorkspaceProjectKeys(workspace: string) {
    const clientsForWorkspace = accessTree[workspace] || {};

    return Object.entries(clientsForWorkspace).flatMap(
      ([client, projects]) =>
        projects.map((project) =>
          makeProjectAccessKey(workspace, client, project)
        )
    );
  }

  function getClientProjectKeys(workspace: string, client: string) {
    return (accessTree[workspace]?.[client] || []).map((project) =>
      makeProjectAccessKey(workspace, client, project)
    );
  }

  function getSelectionState(keys: string[]) {
    const selectedCount = keys.filter((key) =>
      form.project_access.includes(key)
    ).length;

    return {
      checked: keys.length > 0 && selectedCount === keys.length,
      indeterminate:
        keys.length > 0 &&
        selectedCount > 0 &&
        selectedCount < keys.length,
    };
  }

  function getPermissionSelectionState() {
    const selectedCount = permissions.filter((permission) =>
      form.permissions.includes(permission)
    ).length;

    return {
      checked:
        permissions.length > 0 &&
        selectedCount === permissions.length,
      indeterminate:
        permissions.length > 0 &&
        selectedCount > 0 &&
        selectedCount < permissions.length,
    };
  }

  function toggleAllPermissions() {
    setForm((current) => {
      const allSelected = permissions.every((permission) =>
        current.permissions.includes(permission)
      );

      return {
        ...current,
        permissions: allSelected ? [] : [...permissions],
      };
    });
  }

  function syncAccessFromProjects(projectAccess: string[]) {
    const workspaceSet = new Set<string>();
    const clientSet = new Set<string>();

    projectAccess.forEach((projectKey) => {
      const parsed = parseProjectAccessKey(projectKey);

      if (parsed.workspace) {
        workspaceSet.add(parsed.workspace);
      }

      if (parsed.workspace && parsed.client) {
        clientSet.add(
          makeClientAccessKey(parsed.workspace, parsed.client)
        );
      }
    });

    return {
      workspace_access: Array.from(workspaceSet),
      client_access: Array.from(clientSet),
      project_access: projectAccess,
    };
  }

  function toggleProjectAccess(
    workspace: string,
    client: string,
    project: string
  ) {
    const projectKey = makeProjectAccessKey(
      workspace,
      client,
      project
    );

    setForm((current) => {
      const exists = current.project_access.includes(projectKey);

      const nextProjectAccess = exists
        ? current.project_access.filter((item) => item !== projectKey)
        : [...current.project_access, projectKey];

      return {
        ...current,
        ...syncAccessFromProjects(nextProjectAccess),
      };
    });
  }

  function toggleClientAccess(workspace: string, client: string) {
    const projectKeys = getClientProjectKeys(workspace, client);

    setForm((current) => {
      const allSelected =
        projectKeys.length > 0 &&
        projectKeys.every((key) =>
          current.project_access.includes(key)
        );

      const projectSet = new Set(current.project_access);

      if (allSelected) {
        projectKeys.forEach((key) => projectSet.delete(key));
      } else {
        projectKeys.forEach((key) => projectSet.add(key));
      }

      return {
        ...current,
        ...syncAccessFromProjects(Array.from(projectSet)),
      };
    });
  }

  function toggleWorkspaceAccess(workspace: string) {
    const projectKeys = getWorkspaceProjectKeys(workspace);

    setForm((current) => {
      const allSelected =
        projectKeys.length > 0 &&
        projectKeys.every((key) =>
          current.project_access.includes(key)
        );

      const projectSet = new Set(current.project_access);

      if (allSelected) {
        projectKeys.forEach((key) => projectSet.delete(key));
      } else {
        projectKeys.forEach((key) => projectSet.add(key));
      }

      return {
        ...current,
        ...syncAccessFromProjects(Array.from(projectSet)),
      };
    });
  }

  function getErrorMessage(error: any) {
    const rawMessage =
      error?.detail ||
      error?.message ||
      error?.response?.data?.detail ||
      "Unable to save user.";

    const jsonMatch = String(rawMessage).match(/\{.*\}$/);

    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        return parsed?.detail || rawMessage;
      } catch {
        return rawMessage;
      }
    }

    return rawMessage;
  }

  function showUserWarning(title: string, message: string) {
    setUserWarningTitle(title);
    setUserWarningMessage(message);
    setShowUserWarningModal(true);
  }

  function createUser() {
    if (!form.username.trim()) {
      setMessage("Username is required.");
      return;
    }

    if (!form.display_name.trim()) {
      setMessage("User display name is required.");
      return;
    }

    apiPost("/api/users/create", {
      username: form.username,
      display_name: form.display_name,
      password: form.password,
      role: form.role,
      auth_provider:
        form.role === "INSYT Admin"
        ? "local"
        : form.auth_provider,
      status: "active",
      workspace_access: form.workspace_access,
      client_access: form.client_access,
      project_access: form.project_access,
      permissions: form.permissions,
      email: form.email,
    })
      .then((response) => {
        setMessage(response.message || "User access saved.");
        resetForm();
        loadUsers();
      })
      .catch((error) => {
        const errorMessage = getErrorMessage(error);

        if (
          errorMessage.includes("Duplicate Email Detected") ||
          errorMessage.includes("Duplicate Username Detected")
        ) {
          setMessage("");
          showUserWarning("Duplicate User Detected", errorMessage);
          return;
        }

        console.error(error);

        showUserWarning(
          "User Save Failed",
          errorMessage ||
            "Save User Access failed. Check backend /api/users/create."
        );
      });
  }

  function updateUser() {
    if (!form.username.trim()) {
      setMessage("Select or enter a username before updating.");
      return;
    }

    apiPost("/api/users/update", {
      username: form.username,
      display_name: form.display_name,
      password: form.password,
      role: form.role,
      auth_provider:
        form.role === "INSYT Admin"
            ? "local"
            : form.auth_provider,
      workspace_access: form.workspace_access,
      client_access: form.client_access,
      project_access: form.project_access,
      permissions: form.permissions,
      email: form.email,
    })
      .then(() => {
        setMessage("User access updated.");
        resetForm();
        loadUsers();
      })
      .catch((error) => {
        const errorMessage = getErrorMessage(error);

        if (
          errorMessage.includes("Duplicate Email Detected") ||
          errorMessage.includes("Duplicate Username Detected")
        ) {
          setMessage("");
          showUserWarning("Duplicate User Detected", errorMessage);
          return;
        }

        console.error(error);

        showUserWarning(
          "User Update Failed",
          errorMessage || "Update User Access failed."
        );
      });
  }

  function editSelectedUsers() {
    const usernames = Object.keys(selectedUsers).filter(
      (username) => selectedUsers[username]
    );

    if (usernames.length !== 1) {
      alert("Select exactly one user to edit.");
      return;
    }

    const selectedUser = users.find(
      (user) => user.username === usernames[0]
    );

    if (!selectedUser) return;

    const savedProjectAccess = selectedUser.project_access || [];

    const normalizedProjectAccess = savedProjectAccess.map(
      (projectKey) => {
        const parsed = parseProjectAccessKey(projectKey);

        if (parsed.workspace) {
          return projectKey;
        }

        const fallbackWorkspace =
          selectedUser.workspace_access?.[0] || defaultWorkspace;

        if (parsed.client && parsed.project) {
          return makeProjectAccessKey(
            fallbackWorkspace,
            parsed.client,
            parsed.project
          );
        }

        return projectKey;
      }
    );

    const syncedAccess = syncAccessFromProjects(
      normalizedProjectAccess
    );

    setForm({
      display_name: selectedUser.display_name,
      username: selectedUser.username,
      password: "",
      role: selectedUser.role,
      auth_provider: selectedUser.auth_provider || "entra",
      workspace_access: syncedAccess.workspace_access,
      client_access: syncedAccess.client_access,
      project_access: syncedAccess.project_access,
      permissions: selectedUser.permissions || [],
      email: selectedUser.email || "",
    });

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  function deleteSelectedUsers() {
    const usernames = Object.keys(selectedUsers).filter(
      (username) => selectedUsers[username]
    );

    if (usernames.length === 0) return;

    const confirmed = window.confirm(
      `Delete ${usernames.length} selected user(s)?`
    );

    if (!confirmed) return;

    Promise.all(
      usernames.map((username) =>
        apiPost("/api/users/delete", { username })
      )
    ).then(() => {
      setSelectedUsers({});
      loadUsers();
    });
  }


  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="User Access"
          subtitle="Create users and assign Workspace, Client, Project, and Permissions access."
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Add / Edit User Access">
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-4 mb-6">
            <div>
              <FormLabel>User</FormLabel>
              <Input
                value={form.display_name}
                onChange={(value) =>
                  setForm({
                    ...form,
                    display_name: value,
                  })
                }
                placeholder="Display name"
              />
            </div>

            <div>
              <FormLabel>Email</FormLabel>
              <Input
                value={form.email}
                onChange={(value) =>
                  setForm({
                    ...form,
                    email: value,
                  })
                }
                placeholder="user@email.com"
              />
            </div>

            <div>
              <FormLabel>User Name</FormLabel>
              <Input
                value={form.username}
                onChange={(value) =>
                  setForm({
                    ...form,
                    username: value,
                  })
                }
                placeholder="username"
              />
            </div>

            <div>
              <FormLabel>Password</FormLabel>
              <Input
                type="password"
                value={form.password}
                onChange={(value) =>
                  setForm({
                    ...form,
                    password: value,
                  })
                }
                placeholder="temporary password"
              />
            </div>

            <div>
              <FormLabel>Level</FormLabel>
              <Select
                value={form.role}
                onChange={(value) =>
                  setForm({
                    ...form,
                    role: value,
                  })
                }
              >
                {levels.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </Select>
            </div>
            <div>
                <FormLabel>Authentication</FormLabel>

                {isInsytAdminLevel ? (
                    <div className="rounded-lg border border-lime-500/40 bg-lime-500/10 p-3 text-sm text-lime-200">
                    Local INSYT Login + MFA Required
                    </div>
                ) : (
                    <Select
                    value={form.auth_provider}
                    onChange={(value) =>
                        setForm({
                        ...form,
                        auth_provider: value,
                        })
                    }
                    >
                    <option value="entra">
                        Microsoft Entra
                    </option>

                    <option value="local">
                        Local INSYT Login
                    </option>
                    </Select>
                )}
                </div>
          </div>

          {isInsytAdminLevel ? (
            <div className="mb-6 rounded-lg border border-lime-500/40 bg-lime-500/10 p-4 text-lime-200">
                <div className="font-semibold mb-2">
                Full INSYT Platform Access
                </div>

                <div className="text-sm">
                Workspace, Client, Project, and Permission
                selections are not required. INSYT Admin
                users automatically receive access to all
                INSYT modules, clients, projects, and
                administrative functions.
                </div>
            </div>
            ) : (
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
              <div className="xl:col-span-2">
                <h3 className="font-semibold mb-3">
                  Workspace / Client / Project Access
                </h3>

                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 max-h-[420px] overflow-auto">
                  {workspaces.map((workspace) => {
                    const clientsForWorkspace =
                      accessTree[workspace.value] || {};
                    const clientEntries = Object.entries(
                      clientsForWorkspace
                    );
                    const workspaceProjectKeys =
                      getWorkspaceProjectKeys(workspace.value);
                    const workspaceState = getSelectionState(
                      workspaceProjectKeys
                    );
                    const workspaceExpanded =
                      expandedWorkspaces[workspace.value] ?? false;

                    return (
                      <div
                        key={workspace.value}
                        className="border-b border-slate-800 last:border-b-0 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              toggleExpandedWorkspace(workspace.value)
                            }
                            className="w-6 rounded text-slate-300 hover:bg-slate-800"
                          >
                            {workspaceExpanded ? "▾" : "▸"}
                          </button>

                          <input
                            type="checkbox"
                            checked={workspaceState.checked}
                            ref={(input) => {
                              if (input) {
                                input.indeterminate =
                                  workspaceState.indeterminate;
                              }
                            }}
                            onChange={() =>
                              toggleWorkspaceAccess(workspace.value)
                            }
                            className="accent-sky-600"
                          />

                          <span className="font-semibold text-white">
                            {workspace.label}
                          </span>

                          <span className="text-xs text-slate-500">
                            {workspaceProjectKeys.length} project(s)
                          </span>
                        </div>

                        {workspaceExpanded && (
                          <div className="mt-2 ml-8 space-y-2">
                            {clientEntries.length === 0 ? (
                              <p className="text-sm text-slate-500">
                                No clients found for this workspace.
                              </p>
                            ) : (
                              clientEntries.map(([client, projects]) => {
                                const clientKey = makeClientAccessKey(
                                  workspace.value,
                                  client
                                );
                                const clientProjectKeys =
                                  getClientProjectKeys(
                                    workspace.value,
                                    client
                                  );
                                const clientState = getSelectionState(
                                  clientProjectKeys
                                );
                                const clientExpanded =
                                  expandedClients[clientKey] ?? false;

                                return (
                                  <div key={clientKey}>
                                    <div className="flex items-center gap-2">
                                      <button
                                        type="button"
                                        onClick={() =>
                                          toggleExpandedClient(
                                            workspace.value,
                                            client
                                          )
                                        }
                                        className="w-6 rounded text-slate-300 hover:bg-slate-800"
                                      >
                                        {clientExpanded ? "▾" : "▸"}
                                      </button>

                                      <input
                                        type="checkbox"
                                        checked={clientState.checked}
                                        ref={(input) => {
                                          if (input) {
                                            input.indeterminate =
                                              clientState.indeterminate;
                                          }
                                        }}
                                        onChange={() =>
                                          toggleClientAccess(
                                            workspace.value,
                                            client
                                          )
                                        }
                                        className="accent-sky-600"
                                      />

                                      <span className="text-slate-200">
                                        {client}
                                      </span>

                                      <span className="text-xs text-slate-500">
                                        {projects.length} project(s)
                                      </span>
                                    </div>

                                    {clientExpanded && (
                                      <div className="mt-1 ml-8 space-y-1">
                                        {projects.length === 0 ? (
                                          <p className="text-sm text-slate-500">
                                            No projects found for this client.
                                          </p>
                                        ) : (
                                          projects.map((project) => {
                                            const projectKey =
                                              makeProjectAccessKey(
                                                workspace.value,
                                                client,
                                                project
                                              );

                                            return (
                                              <label
                                                key={projectKey}
                                                className="flex items-center gap-2 text-sm text-slate-300"
                                              >
                                                <input
                                                  type="checkbox"
                                                  checked={form.project_access.includes(
                                                    projectKey
                                                  )}
                                                  onChange={() =>
                                                    toggleProjectAccess(
                                                      workspace.value,
                                                      client,
                                                      project
                                                    )
                                                  }
                                                  className="accent-sky-600"
                                                />

                                                <span>
                                                  {project.replaceAll(
                                                    "_",
                                                    " "
                                                  )}
                                                </span>
                                              </label>
                                            );
                                          })
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <p className="mt-2 text-xs text-slate-500">
                  Select workspaces, clients, or individual projects.
                  Partial selections are shown automatically.
                </p>
              </div>

              <div>
                <h3 className="font-semibold mb-3">
                  Permissions
                </h3>

                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  {(() => {
                    const permissionState = getPermissionSelectionState();

                    return (
                      <>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setPermissionsExpanded(
                                (current) => !current
                              )
                            }
                            className="w-6 rounded text-slate-300 hover:bg-slate-800"
                          >
                            {permissionsExpanded ? "▾" : "▸"}
                          </button>

                          <input
                            type="checkbox"
                            checked={permissionState.checked}
                            ref={(input) => {
                              if (input) {
                                input.indeterminate =
                                  permissionState.indeterminate;
                              }
                            }}
                            onChange={toggleAllPermissions}
                            className="accent-sky-600"
                          />

                          <span className="font-semibold text-white">
                            Permissions
                          </span>

                          <span className="text-xs text-slate-500">
                            {form.permissions.length} selected
                          </span>
                        </div>

                        {permissionsExpanded && (
                          <div className="mt-3 ml-8 space-y-1">
                            {permissions.map((permission) => (
                              <label
                                key={permission}
                                className="flex items-center gap-2 text-sm text-slate-300"
                              >
                                <input
                                  type="checkbox"
                                  checked={form.permissions.includes(
                                    permission
                                  )}
                                  onChange={() =>
                                    toggleArrayValue(
                                      "permissions",
                                      permission
                                    )
                                  }
                                  className="accent-sky-600"
                                />

                                <span>{permission}</span>
                              </label>
                            ))}
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>

                <p className="mt-2 text-xs text-slate-500">
                  Expand to select individual permissions, or use
                  the parent checkbox to select all.
                </p>
              </div>
            </div>
            )}

          <div className="flex gap-3">
            <Button onClick={createUser}>
              Save User Access
            </Button>

            <Button
              variant="secondary"
              onClick={updateUser}
            >
              Update User Access
            </Button>
          </div>
        </ContentCard>

        <div className="mt-6">
          <ContentCard title="Existing Users">
            <div className="mb-4 flex gap-3">
              <Button
                variant="secondary"
                onClick={editSelectedUsers}
              >
                Edit Selected
              </Button>

              <Button
                variant="danger"
                onClick={deleteSelectedUsers}
              >
                Delete Selected
              </Button>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[65vh] w-full">
              <table className="w-full text-xs table-auto">
                <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                  <tr>
                    <th className="p-3 text-left">Select</th>
                    <th className="p-3 text-left">User</th>
                    <th className="p-3 text-left">Email</th>
                    <th className="p-3 text-left">Level</th>
                    <th className="p-3 text-left">Authentication</th>
                    <th className="p-3 text-left">User Name</th>
                    <th className="p-3 text-left">Password</th>
                    <th className="p-3 text-left">Workspace</th>
                    <th className="p-3 text-left">Client</th>
                    <th className="p-3 text-left">Project</th>
                    <th className="p-3 text-left">Permissions</th>
                  </tr>
                </thead>

                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.username}
                      className="border-t border-slate-800"
                    >
                      <td className="p-3">
                        <input
                          type="checkbox"
                          checked={Boolean(
                            selectedUsers[user.username]
                          )}
                          onChange={(event) =>
                            setSelectedUsers({
                              ...selectedUsers,
                              [user.username]:
                                event.target.checked,
                            })
                          }
                          className="accent-sky-600"
                        />
                      </td>

                      <td className="p-3 text-white">
                        {user.display_name}
                      </td>

                      <td className="p-3 text-slate-300">
                        {user.email || "—"}
                      </td>

                      <td className="p-3 text-slate-300">
                        {user.role}
                      </td>

                      <td className="p-3 text-slate-300">
                        {user.auth_provider || "local"}
                      </td>

                      <td className="p-3 text-slate-300">
                        {user.username}
                      </td>

                      <td className="p-3 text-slate-500">
                        ********
                      </td>

                      <td className="p-3 text-slate-300 max-w-[180px] break-words">
                        {(user.workspace_access || []).join(", ") ||
                          "—"}
                      </td>

                      <td className="p-3 text-slate-300 max-w-[180px] break-words">
                        {(user.client_access || []).join(", ") ||
                          "—"}
                      </td>

                      <td className="p-3 text-slate-300 max-w-[260px] break-words">
                        {(user.project_access || [])
                          .map((project) => {
                            const parsed = parseProjectAccessKey(project);

                            if (
                              parsed.workspace &&
                              parsed.client &&
                              parsed.project
                            ) {
                              return `${parsed.workspace} / ${parsed.client} / ${parsed.project.replaceAll(
                                "_",
                                " "
                              )}`;
                            }

                            return project.replaceAll("_", " ");
                          })
                          .join(", ") || "—"}
                      </td>

                      <td className="p-3 text-slate-300 max-w-[260px] break-words">
                        {(user.permissions || []).join(", ") ||
                          "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ContentCard>
        </div>
      </PageContainer>

      {showUserWarningModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-950 p-6 shadow-2xl">
            <h2 className="text-lg font-semibold text-white">
              {userWarningTitle}
            </h2>

            <p className="mt-3 text-sm leading-6 text-slate-300">
              {userWarningMessage}
            </p>

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setShowUserWarningModal(false)}
                className="rounded-full bg-sky-500 px-5 py-2 text-sm font-semibold text-white hover:bg-sky-400"
              >
                Acknowledge
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default function UserAccessPage() {
  return (
    <Suspense fallback={<div>Loading user access...</div>}>
      <UserAccessPageContent />
    </Suspense>
  );
}
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
  { value: "development", label: "INSYT Development" },
];

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
  const [clients, setClients] = useState<string[]>([]);
  const [projectsByClient, setProjectsByClient] = useState<
    Record<string, string[]>
  >({});

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

  const selectedWorkspace =
    form.workspace_access[0] || defaultWorkspace;

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

  function loadClients(workspace: string) {
    if (!workspace) {
      setClients([]);
      return;
    }

    apiGet(`/api/${workspace}/clients`)
      .then((response: any) => {
        setClients(response.clients || []);
      })
      .catch((error) => {
        console.error(error);
        setClients([]);
        setMessage("Failed to load clients for workspace.");
      });
  }

  function loadProjectsForClient(
    workspace: string,
    client: string
  ) {
    if (!workspace || !client) return;

    apiGet(
      `/api/${workspace}/clients/${encodeURIComponent(
        client
      )}/projects`
    )
      .then((response: any) => {
        setProjectsByClient((current) => ({
          ...current,
          [client]: response.projects || [],
        }));
      })
      .catch((error) => {
        console.error(error);
        setProjectsByClient((current) => ({
          ...current,
          [client]: [],
        }));
      });
  }

  useEffect(() => {
    loadUsers();
  }, []);

  useEffect(() => {
    loadClients(selectedWorkspace);

    setForm((current) => ({
      ...current,
      client_access: [],
      project_access: [],
    }));

    setProjectsByClient({});
  }, [selectedWorkspace]);

  useEffect(() => {
    form.client_access.forEach((client) => {
      if (!projectsByClient[client]) {
        loadProjectsForClient(selectedWorkspace, client);
      }
    });
  }, [form.client_access, selectedWorkspace]);

  function setWorkspace(value: string) {
    setForm((current) => ({
      ...current,
      workspace_access: [value],
      client_access: [],
      project_access: [],
    }));
    setProjectsByClient({});
  }

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

    const userWorkspace =
      selectedUser.workspace_access?.[0] || defaultWorkspace;

    setForm({
        display_name: selectedUser.display_name,
        username: selectedUser.username,
        password: "",
        role: selectedUser.role,
        auth_provider:
            selectedUser.auth_provider || "entra",
        workspace_access: [userWorkspace],
        client_access: selectedUser.client_access || [],
        project_access: selectedUser.project_access || [],
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

  const visibleProjects = form.client_access.flatMap(
    (client) =>
      (projectsByClient[client] || []).map((project) => ({
        client,
        project,
        key: `${client}/${project}`,
      }))
  );

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
            <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 mb-6">
                <div>
                <h3 className="font-semibold mb-3">
                    Workspace
                </h3>

                <Select
                    value={selectedWorkspace}
                    onChange={setWorkspace}
                >
                    {workspaces.map((workspace) => (
                    <option
                        key={workspace.value}
                        value={workspace.value}
                    >
                        {workspace.label}
                    </option>
                    ))}
                </Select>
                </div>

                <div>
                <h3 className="font-semibold mb-3">
                    Clients
                </h3>

                {clients.length === 0 ? (
                    <p className="text-sm text-slate-500">
                    No clients found for this workspace.
                    </p>
                ) : (
                    clients.map((client) => (
                    <Checkbox
                        key={client}
                        label={client}
                        checked={form.client_access.includes(client)}
                        onChange={() =>
                        toggleArrayValue(
                            "client_access",
                            client
                        )
                        }
                    />
                    ))
                )}
                </div>

                <div>
                <h3 className="font-semibold mb-3">
                    Projects
                </h3>

                {visibleProjects.length === 0 ? (
                    <p className="text-sm text-slate-500">
                    Select one or more clients to load
                    projects.
                    </p>
                ) : (
                    visibleProjects.map(
                    ({ client, project, key }) => (
                        <Checkbox
                        key={key}
                        label={`${client} / ${project.replaceAll(
                            "_",
                            " "
                        )}`}
                        checked={form.project_access.includes(
                            key
                        )}
                        onChange={() =>
                            toggleArrayValue(
                            "project_access",
                            key
                            )
                        }
                        />
                    )
                    )
                )}
                </div>

                <div>
                <h3 className="font-semibold mb-3">
                    Permissions
                </h3>

                {permissions.map((permission) => (
                    <Checkbox
                    key={permission}
                    label={permission}
                    checked={form.permissions.includes(
                        permission
                    )}
                    onChange={() =>
                        toggleArrayValue(
                        "permissions",
                        permission
                        )
                    }
                    />
                ))}
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
                          .map((project) =>
                            project.replaceAll("_", " ")
                          )
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
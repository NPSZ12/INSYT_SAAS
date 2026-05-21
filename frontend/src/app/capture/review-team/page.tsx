"use client";

import { useEffect, useState } from "react";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import Input from "../../../components/Input";
import Select from "../../../components/Select";
import FormLabel from "../../../components/FormLabel";
import Checkbox from "../../../components/Checkbox";
import { apiGet, apiPost } from "../../../lib/api";

type AccessUser = {
  username: string;
  display_name: string;
  email?: string;
  password?: string;
  role: string;
  status: string;
  project_access: string[];
  launches?: string[];
  permissions?: string[];
};

const levels = ["1L", "QC", "TL", "Client", "Admin"];

const launches = [
  "INSYT™ Capture",
  "INSYT™ Discovery",
  "INSYT™ Summaries",
  "INSYT™ Developer",
];

const permissions = [
  "Download Docs",
  "Upload Docs",
  "Edit Captured Entities",
  "Delete Captured Entities",
  "Create Batches",
  "Create Search Folders",
  "View Messaging",
  "Send Messaging",
];

export default function UserAccessPage() {
  const [users, setUsers] = useState<AccessUser[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedUsers, setSelectedUsers] = useState<Record<string, boolean>>({});

  const [form, setForm] = useState({
    display_name: "",
    email: "",
    username: "",
    password: "",
    role: "1L",
    project_access: [] as string[],
    launches: ["INSYT Capture"] as string[],
    permissions: [] as string[],
  });

  function loadData() {
    apiGet("/api/users")
      .then((response) => {
        setUsers(Array.isArray(response) ? response : response.users || []);
      })
      .catch(console.error);

    apiGet("/api/azure-projects")
      .then((data) => {
        if (Array.isArray(data)) {
          setProjects(data);
          return;
        }

        if (Array.isArray(data.projects)) {
          setProjects(data.projects);
          return;
        }

        console.error("Unexpected projects response:", data);
        setProjects([]);
      })
      .catch((error) => {
        console.error("Failed to load Azure projects:", error);
        setProjects([]);
      });
  }

  useEffect(() => {
    loadData();
  }, []);

  function toggleArrayValue(key: "project_access" | "launches" | "permissions", value: string) {
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

  function createUser() {
    apiPost("/api/users/create", {
      username: form.username,
      display_name: form.display_name,
      password: form.password,
      role: form.role,
      project_access: form.project_access,
      launches: form.launches,
      permissions: form.permissions,
      email: form.email,
    })
      .then(() => {
        setForm({
          display_name: "",
          username: "",
          password: "",
          role: "1L",
          project_access: [],
          launches: ["INSYT™ Capture"],
          permissions: [],
          email: "",
        });
        loadData();
      })
      .catch(console.error);
  }

  function updateUser() {
    apiPost("/api/users/update", {
      username: form.username,
      display_name: form.display_name,
      password: form.password,
      role: form.role,
      project_access: form.project_access,
      launches: form.launches,
      permissions: form.permissions,
      email: form.email,
    })
      .then(() => {
        loadData();

        setForm({
          display_name: "",
          username: "",
          password: "",
          role: "1L",
          project_access: [],
          launches: ["INSYT™ Capture"],
          permissions: [],
          email: "",
        });
      })
      .catch(console.error);
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

    if (!selectedUser) {
      return;
    }

    setForm({
      display_name: selectedUser.display_name,
      username: selectedUser.username,
      password: "",
      role: selectedUser.role,
      project_access: selectedUser.project_access || [],
      launches: selectedUser.launches || [],
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
      loadData();
    });
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="User Access"
          subtitle="Manage launch access, user levels, project permissions, passwords, and security rights."
        />

        <ContentCard title="Add / Edit User Access">
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-4 mb-6">
            <div>
              <FormLabel>User</FormLabel>
              <Input
                value={form.display_name}
                onChange={(value) => setForm({ ...form, display_name: value })}
                placeholder="Display name"
              />
            </div>
            <div>
              <FormLabel>Email</FormLabel>
              <Input
                value={form.email}
                onChange={(value) => setForm({ ...form, email: value })}
                placeholder="user@email.com"
              />
            </div>

            <div>
              <FormLabel>User Name</FormLabel>
              <Input
                value={form.username}
                onChange={(value) => setForm({ ...form, username: value })}
                placeholder="username"
              />
            </div>

            <div>
              <FormLabel>Password</FormLabel>
              <Input
                type="password"
                value={form.password}
                onChange={(value) => setForm({ ...form, password: value })}
                placeholder="temporary password"
              />
            </div>

            <div>
              <FormLabel>Level</FormLabel>
              <Select
                value={form.role}
                onChange={(value) => setForm({ ...form, role: value })}
              >
                {levels.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
            <div>
              <h3 className="font-semibold mb-3">Launch Access</h3>
              {launches.map((launch) => (
                <Checkbox
                  key={launch}
                  label={launch}
                  checked={form.launches.includes(launch)}
                  onChange={() => toggleArrayValue("launches", launch)}
                />
              ))}
            </div>

            <div>
              <h3 className="font-semibold mb-3">Projects</h3>
              {(projects || []).map((project) => (
                <Checkbox
                  key={project}
                  label={project.replaceAll("_", " ")}
                  checked={form.project_access.includes(project)}
                  onChange={() => toggleArrayValue("project_access", project)}
                />
              ))}
            </div>

            <div>
              <h3 className="font-semibold mb-3">Permissions</h3>
              {permissions.map((permission) => (
                <Checkbox
                  key={permission}
                  label={permission}
                  checked={form.permissions.includes(permission)}
                  onChange={() => toggleArrayValue("permissions", permission)}
                />
              ))}
            </div>
          </div>

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
                    <th className="p-3 text-left">User Name</th>
                    <th className="p-3 text-left">Password</th>
                    <th className="p-3 text-left">Projects</th>
                    <th className="p-3 text-left">Permissions</th>
                  </tr>
                </thead>

                <tbody>
                  {users.map((user) => (
                    <tr key={user.username} className="border-t border-slate-800">
                      <td className="p-3">
                        <input
                          type="checkbox"
                          checked={Boolean(selectedUsers[user.username])}
                          onChange={(event) =>
                            setSelectedUsers({
                              ...selectedUsers,
                              [user.username]: event.target.checked,
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
                        {user.username}
                      </td>

                      <td className="p-3 text-slate-500">
                        ********
                      </td>

                      <td className="p-3 text-slate-300 max-w-[250px] break-words">
                        {(user.project_access || [])
                          .map((project) => project.replaceAll("_", " "))
                          .join(", ") || "—"}
                      </td>

                      <td className="p-3 text-slate-300 max-w-[250px] break-words">
                        {(user.permissions || []).join(", ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ContentCard>
        </div>
      </PageContainer>
    </AppShell>
  );
}












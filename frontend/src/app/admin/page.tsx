"use client";

import { Suspense, useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import PageHeader from "../../components/PageHeader";
import PageContainer from "../../components/PageContainer";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import Select from "../../components/Select";
import FormLabel from "../../components/FormLabel";
import Checkbox from "../../components/Checkbox";
import { apiGet, apiPost } from "../../lib/api";
import type { User } from "../../types";

function AdminPageContent() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUsername, setSelectedUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [newUser, setNewUser] = useState({
    username: "",
    display_name: "",
    role: "1L Reviewer",
    password: "",
  });

  const projects = [
    { id: "Project_Timber", name: "Project Timber" },
    { id: "Alpine_Claims", name: "Alpine Claims" },
    { id: "Medical_Summary_Demo", name: "Medical Summary Demo" },
  ];

  function loadUsers() {
    apiGet("/api/users/")
      .then((response) => {
        setUsers(Array.isArray(response) ? response : response.users || []);
      })
      .catch(console.error);
  }

  useEffect(() => {
    loadUsers();
  }, []);

  function createUser() {
    apiPost("/api/users/create", {
      ...newUser,
      project_access: [],
    })
      .then(() => {
        setNewUser({
          username: "",
          display_name: "",
          role: "1L Reviewer",
          password: "",
        });
        loadUsers();
      })
      .catch(console.error);
  }

  function resetPassword() {
    apiPost("/api/users/reset-password", {
      username: selectedUsername,
      new_password: newPassword,
    })
      .then(() => {
        setNewPassword("");
        alert("Password reset submitted.");
      })
      .catch(console.error);
  }

  function updateProjectAccess(
    username: string,
    projectId: string,
    allowed: boolean
  ) {
    apiPost("/api/users/project-access", {
      username,
      project_id: projectId,
      allowed,
    })
      .then(loadUsers)
      .catch(console.error);
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Admin"
          subtitle="Manage user credentials, roles, passwords, and project access."
        />

        <div className="grid grid-cols-2 gap-6 mb-6">
          <ContentCard title="Create User Credential">
            <FormLabel>Username</FormLabel>
            <div className="mb-4">
              <Input
                value={newUser.username}
                onChange={(value) =>
                  setNewUser({ ...newUser, username: value })
                }
              />
            </div>

            <FormLabel>Display Name</FormLabel>
            <div className="mb-4">
              <Input
                value={newUser.display_name}
                onChange={(value) =>
                  setNewUser({ ...newUser, display_name: value })
                }
              />
            </div>

            <FormLabel>Role</FormLabel>
            <div className="mb-4">
              <Select
                value={newUser.role}
                onChange={(value) =>
                  setNewUser({ ...newUser, role: value })
                }
              >
                <option>INSYT Admin</option>
                <option>RM</option>
                <option>TL</option>
                <option>QC</option>
                <option>1L Reviewer</option>
              </Select>
            </div>

            <FormLabel>Temporary Password</FormLabel>
            <div className="mb-6">
              <Input
                type="password"
                value={newUser.password}
                onChange={(value) =>
                  setNewUser({ ...newUser, password: value })
                }
              />
            </div>

            <Button fullWidth onClick={createUser}>
              Create User
            </Button>
          </ContentCard>

          <ContentCard title="Reset Password">
            <FormLabel>User</FormLabel>
            <div className="mb-4">
              <Select
                value={selectedUsername}
                onChange={setSelectedUsername}
              >
                <option value="">Select User</option>
                {users.map((user) => (
                  <option key={user.username} value={user.username}>
                    {user.display_name} ({user.username})
                  </option>
                ))}
              </Select>
            </div>

            <FormLabel>New Password</FormLabel>
            <div className="mb-6">
              <Input
                type="password"
                value={newPassword}
                onChange={setNewPassword}
              />
            </div>

            <Button fullWidth onClick={resetPassword}>
              Reset Password
            </Button>
          </ContentCard>
        </div>

        <ContentCard title="Project Access Control">
          <div className="space-y-6">
            {users.map((user) => (
              <div
                key={user.username}
                className="bg-slate-950 border border-slate-800 rounded-xl p-5"
              >
                <div className="flex justify-between mb-4">
                  <div>
                    <h3 className="font-semibold text-white">
                      {user.display_name}
                    </h3>
                    <p className="text-sm text-slate-400">
                      {user.username} · {user.role}
                    </p>
                  </div>

                  <span className="text-xs bg-lime-50 px-3 py-1 rounded-full h-fit">
                    {user.status}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  {(projects || []).map((project) => (
                    <Checkbox
                      key={project.id}
                      label={project.name}
                      checked={user.project_access.includes(project.id)}
                      onChange={(checked) =>
                        updateProjectAccess(
                          user.username,
                          project.id,
                          checked
                        )
                      }
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}


export default function AdminPage() {
  return (
    <Suspense fallback={<div>Loading admin...</div>}>
      <AdminPageContent />
    </Suspense>
  );
}






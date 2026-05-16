import type { Project, User } from "../types";

export const projects: Project[] = [
  {
    name: "Project Timber",
    client: "Builders FirstSource",
    status: "Active",
    docs: "1,189",
    qc: "87%",
  },
  {
    name: "Alpine Claims",
    client: "BFS / Alpine",
    status: "QC Review",
    docs: "436",
    qc: "72%",
  },
  {
    name: "Medical Summary Demo",
    client: "INSYT Internal",
    status: "Ready",
    docs: "58",
    qc: "100%",
  },
];

export const users: User[] = [
  {
    username: "Nathaniel",
    display_name: "Nathaniel Swearingen",
    email: "nathaniel@insyt360.com",
    role: "INSYT Admin",
    status: "Active",
    project_access: [],
    launches: [],
    permissions: [],
  },
  {
    username: "reviewer1",
    display_name: "Reviewer One",
    email: "reviewer1@insyt360.com",
    role: "1L Reviewer",
    status: "Active",
    project_access: [],
    launches: [],
    permissions: [],
  },
  {
    username: "qclead",
    display_name: "QC Lead",
    email: "qclead@insyt360.com",
    role: "QC",
    status: "Active",
    project_access: [],
    launches: [],
    permissions: [],
  },
  {
    username: "teamlead",
    display_name: "Team Lead",
    email: "teamlead@insyt360.com",
    role: "TL",
    status: "Inactive",
    project_access: [],
    launches: [],
    permissions: [],
  },
];
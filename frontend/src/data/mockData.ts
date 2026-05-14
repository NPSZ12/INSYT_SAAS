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
    client: "CDS Internal",
    status: "Ready",
    docs: "58",
    qc: "100%",
  },
];

export const users: User[] = [
  {
    name: "Nathaniel Swearingen",
    role: "CDS Admin",
    status: "Active",
  },
  {
    name: "Reviewer One",
    role: "1L Reviewer",
    status: "Active",
  },
  {
    name: "QC Lead",
    role: "QC",
    status: "Active",
  },
  {
    name: "Team Lead",
    role: "TL",
    status: "Inactive",
  },
];
export type Project = {
  name: string;
  client: string;
  status: string;
  docs: string;
  qc: string;
};

export type User = {
  username: string;
  display_name: string;
  email: string;
  role: string;
  status: string;
  project_access: string[];
  launches: string[];
  permissions: string[];
};

export type ReviewDocument = {
  project: string;
  project_id?: string;
  batch: string;
  doc_id: string;
  blob_name?: string;
  native_blob?: string;
  native_url?: string;
  text: string;
  fields: {
    section: string;
    label: string;
    type: string;
    format?: string;
    notes?: string;
  }[];
};

export type AzureProject = string;
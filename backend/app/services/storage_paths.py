def clean_path_part(value: str | None) -> str:
    return str(value or "").strip().replace("\\", "/").strip("/")


def build_project_storage_key(value: str | None) -> str:
    return clean_path_part(value).replace(" ", "_")


def build_project_base_path(
    workspace: str,
    client: str,
    project: str,
) -> str:
    workspace_name = clean_path_part(workspace).lower() or "capture"
    client_name = clean_path_part(client)
    project_name = build_project_storage_key(project)

    return f"{client_name}/{workspace_name}/{project_name}"


def build_project_path(
    workspace: str,
    client: str,
    project: str,
    *parts: str,
) -> str:
    base_path = build_project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    clean_parts = [
        clean_path_part(part)
        for part in parts
        if clean_path_part(part)
    ]

    if not clean_parts:
        return base_path

    return f"{base_path}/{'/'.join(clean_parts)}"


def normalize_project_storage_key(project: str) -> str:
    value = (project or "").strip().strip("/")

    if not value:
        raise ValueError("Project is required.")

    return value.replace(" ", "_")


def build_project_prefix(
    workspace: str,
    client: str,
    project: str,
    folder: str | None = None,
) -> str:
    workspace_clean = (workspace or "").strip().lower().strip("/")
    client_clean = (client or "").strip().strip("/")
    project_storage_key = normalize_project_storage_key(project)

    parts = [
        client_clean,
        workspace_clean,
        project_storage_key,
    ]

    if folder:
        folder_clean = folder.strip().strip("/")
        if folder_clean:
            parts.append(folder_clean)

    return "/".join(parts).rstrip("/") + "/"

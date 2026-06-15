def clean_path_part(value: str | None) -> str:
    return str(value or "").strip().strip("/")


def build_project_base_path(
    workspace: str,
    client: str,
    project: str,
) -> str:
    workspace_name = clean_path_part(workspace)
    client_name = clean_path_part(client)
    project_name = clean_path_part(project)

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


def build_project_prefix(
    workspace: str,
    client: str,
    project: str,
    *parts: str,
) -> str:
    path = build_project_path(
        workspace,
        client,
        project,
        *parts,
    )

    return f"{path}/"
import pandas as pd
from pathlib import Path


def load_protocol_fields(project_id: str):
    protocol_path = Path(
        f"C:/INSYT_SAAS/backend/data/projects/{project_id}/{project_id}_Protocol.xlsx"
    )

    if not protocol_path.exists():
        return []

    df = pd.read_excel(protocol_path)

    fields = []
    current_section = ""

    for _, row in df.iterrows():
        raw_section = row.get("Section", "")
        section = "" if pd.isna(raw_section) else str(raw_section).strip()

        if section:
            current_section = section
        else:
            section = current_section

    for _, row in df.iterrows():
        raw_section = row.get("Section", "")
        section = "" if pd.isna(raw_section) else str(raw_section).strip()

        raw_data_element = row.get("Data Element", "")
        data_element = "" if pd.isna(raw_data_element) else str(raw_data_element).strip()

        raw_field_format = row.get("Format", "")
        field_format = "" if pd.isna(raw_field_format) else str(raw_field_format).strip()

        raw_notes = row.get("Notes", "")
        notes = "" if pd.isna(raw_notes) else str(raw_notes).strip()

        if not data_element:
            continue

        if "entity tag" in field_format.lower():
            field_type = "checkbox"
        elif "text capture" in field_format.lower():
            field_type = "textarea"
        else:
            field_type = "text"

        fields.append({
            "section": section,
            "label": data_element,
            "type": field_type,
            "format": field_format,
            "notes": notes,
        })

    return fields
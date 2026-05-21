import os, zipfile

root = r"C:\INSYT_SAAS\frontend"
zip_path = os.path.join(root, "deploy.zip")

exclude_dirs = {"node_modules", ".next", ".git", "deploy_frontend"}
exclude_files = {"deploy.zip", ".env.local"}

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file in exclude_files:
                continue
            full = os.path.join(folder, file)
            rel = os.path.relpath(full, root).replace("\\", "/")
            z.write(full, rel)

print("Created:", zip_path)

# Upload this project to GitHub

Suggested repository name: `inventory-expiry-tracker`

## Repository description

A full-stack inventory and expiry tracker with batch-level stock, FEFO picking, quarantined returns, CSV/XLSX imports, alerts, and audit logs. Built with React, TypeScript, FastAPI, and PostgreSQL.

## Upload through the GitHub website

1. Extract `Stockroom-GitHub.zip` on your computer.
2. Create a new repository named `inventory-expiry-tracker`. Paste the description above and choose the visibility you want. Leave the automatic README, license, and gitignore options unchecked because the project already includes its README and gitignore; choose a license separately if you want one.
3. Open the repository's upload-files page and upload the **contents** of the extracted `Stockroom` folder. The README, backend, frontend, docs, scripts and templates should be at the repository root. Uploading the ZIP itself does not unpack the project on GitHub.
4. Include the hidden `.gitignore`, `.dockerignore`, and `.env.example` files. On macOS, press Command+Shift+Period in Finder to show hidden files. If your browser omits them, use the Git method below.
5. Commit the uploaded files with a message such as `Initial Stockroom implementation`.

## Upload using Git

Run these commands inside the extracted Stockroom folder, replacing YOUR_USERNAME with your GitHub username. Create the empty repository on GitHub first.

```sh
git init
git add .
git commit -m "Initial Stockroom implementation"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/inventory-expiry-tracker.git
git push -u origin main
```

The ZIP contains source, dependency lockfiles, migrations, tests, templates, and setup documentation. It excludes the local demo account/password, PostgreSQL database, installed dependencies, virtual environment, caches, screenshots, and generated frontend build. Anyone cloning the repository must follow README.md to install dependencies and create their own account.

Suggested topics: `inventory-management`, `expiry-tracking`, `fefo`, `react`, `typescript`, `fastapi`, `postgresql`.

No GitHub repository has been created or uploaded automatically.

# MiniCloud — Personal Cloud Storage

MiniCloud is a learning project built with Python, Flask, Flask-Login, SQLAlchemy, SQLite, HTML, CSS, and JavaScript.

## Features
- Account signup and login
- Private file uploads, downloads, image preview, and deletion
- Nested folder organization
- Storage usage meter and file search
- Upload progress indicator
- Secure, random share tokens
- Optional share-link password, expiry (24 hours / 7 days / 30 days), and download limit
- Revoke sharing links
- Health endpoint at `/health`

## Run locally (Windows PowerShell)
1. Install Python 3.11+ if it is not already installed.
2. Open PowerShell in the project folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Start the app:

   ```powershell
   python app.py
   ```

6. Open `http://127.0.0.1:5000`.

## Existing MiniCloud database
The app uses `minicloud.db` and an `uploads` directory next to `app.py`. Back them up before replacing code. Do not commit the database or uploaded files to GitHub.

## Important security notes
- Set a strong random `MINICLOUD_SECRET_KEY` environment variable before any deployment.
- Use HTTPS in public hosting.
- The development server is for local development only. Use a production WSGI server for public deployment.
- Public links must use a publicly reachable deployment URL; `127.0.0.1` links work only on the local computer.
- Do not put real user data in a public demo. Test with non-sensitive files.

## GitHub checklist
1. Copy the final app code into `app.py`.
2. Rename `MiniCloud_requirements.txt` to `requirements.txt`.
3. Rename `MiniCloud_gitignore.txt` to `.gitignore`.
4. Add a README.md containing this documentation.
5. Confirm `minicloud.db`, `uploads/`, `.env`, and virtual environments are ignored.
6. In VS Code Source Control, review the files before committing.
7. Push only code and documentation, never private uploads or database files.

## Suggested test plan
- Create an account and log in/out.
- Upload, preview, download, and delete a non-sensitive test file.
- Create a folder and upload a file into it.
- Generate a share link without a password and download in a private window.
- Generate a password-protected link and test both correct and incorrect passwords.
- Test expiry and download limit using a test link.
- Revoke a link and confirm it returns a not-found page.

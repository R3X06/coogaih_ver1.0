# Coogaih — Git Manual

*Your personal reference. Come back here whenever you're unsure what to run.*

---

## 1. The core mental model

```
Your laptop  ←──────→  GitHub (the "remote")  ←──────→  His laptop
(local repo)              source of truth               (local repo)
```

Nothing moves directly between laptops. Everything goes **through** GitHub.
- **Push** = send your commits up to GitHub
- **Pull** = bring GitHub's commits down to you
- Nothing syncs automatically, ever. You always have to run the command.

## 2. The four stages of a change

| Stage | What it means | Command |
|---|---|---|
| Working directory | Files on disk, however messy | *(just editing)* |
| Staged | Marked "include in next commit" | `git add` |
| Committed | Saved as a permanent snapshot — **locally only** | `git commit` |
| Pushed | Sent up to GitHub | `git push` |

A commit does **not** reach GitHub or your friend until you push it.

## 3. Why branches, and why `main` is protected

`main` is the official, always-working version of the project. It's protected — you can't push to it directly, and merging in requires a Pull Request (PR), and if the change touches `docs/DATA_CONTRACT.md` or `docs/API_CONTRACT.md`, both you and your friend must approve (enforced by `.github/CODEOWNERS`).

Every task — a feature, a fix, an experiment — gets its own **branch**: a disposable side-copy where you can commit freely without touching the official version until it's ready and reviewed.

---

## 4. The daily workflow, step by step

### Step 0 — Before starting anything new, sync up
```powershell
git checkout main
git pull
```
Make sure you're building on the latest merged code.

### Step 1 — Create a branch for the task
```powershell
git checkout -b R3X06/short-description
```
One branch per task. Name it so future-you knows what it was for.

### Step 2 — Do the work
Edit files normally in VS Code.

### Step 3 — Check what changed
```powershell
git status
```
Run this constantly — before staging, before committing, after pulling. It costs nothing.

### Step 4 — Stage the changes
```powershell
git add .
```
(`.` = everything in this folder. Use `git add <filename>` to stage just one file.)

### Step 5 — Commit
```powershell
git commit -m "Describe what changed, briefly"
```
This is local only — nothing on GitHub yet.

### Step 6 — Push the branch
```powershell
git push -u origin R3X06/short-description
```
`-u` is only needed the first time on a new branch — after that, plain `git push` works on this branch.

### Step 7 — Open a Pull Request
GitHub prints a link in the terminal after pushing, or go to the repo on GitHub — a yellow banner offers "Compare & pull request." Click it, add a title, click **Create pull request**.

### Step 8 — Merge
- Solo change, doesn't touch shared contract docs → review your own diff, click **Merge pull request** → **Confirm**.
- Touches `docs/DATA_CONTRACT.md` or `docs/API_CONTRACT.md` → your friend must approve first; merge unlocks once he does.

### Step 9 — Sync back up and clean up
```powershell
git checkout main
git pull
git branch -d R3X06/short-description
```
`-d` only deletes the branch if its commits are already merged into `main` — Git refuses otherwise, so you can't accidentally lose unmerged work this way. The commits themselves aren't lost when this succeeds; they already live inside `main`'s history. This is just removing the leftover label.

### Step 10 — Start the next task
```powershell
git checkout -b R3X06/next-thing
```
Never reuse an old branch for unrelated new work.

---

## 5. Getting his changes into your work

**Simple case — you just want the latest `main`:**
```powershell
git checkout main
git pull
```

**You're mid-work on your own branch and want his latest `main` merged in** (so you don't drift too far apart):
```powershell
git checkout main
git pull
git checkout your-branch-name
git merge main
```

**If a merge conflict happens** (you both edited the same lines of the same file — rare given your folder split, but possible in `docs/`): Git marks the conflicting section with `<<<<<<<` / `=======` / `>>>>>>>`. Open the file, manually decide the final version, delete the markers, then:
```powershell
git add .
git commit -m "Merge main into branch, resolve conflict"
```

---

## 6. Verifying you're actually connected to GitHub

```powershell
git remote -v
```
Should print the repo URL twice (fetch + push). If this errors or prints nothing, your folder isn't connected to GitHub — see §8.

```powershell
git status
```
`working tree clean` = everything on disk matches your last commit. Anything under "Untracked" or "Changes not staged" exists locally but isn't committed yet.

```powershell
git log --oneline -5
```
Shows your last 5 commits — sanity check that history looks right.

---

## 7. Quick reference card

| Command | What it does |
|---|---|
| `git status` | What's changed, staged or not |
| `git add .` | Stage everything |
| `git add <file>` | Stage one file |
| `git commit -m "..."` | Save a local snapshot |
| `git push` | Send commits to GitHub |
| `git push -u origin <branch>` | Push a new branch for the first time |
| `git pull` | Bring GitHub's commits to you |
| `git checkout -b <name>` | Create + switch to a new branch |
| `git checkout main` | Switch to `main` |
| `git checkout <branch>` | Switch to any existing branch |
| `git branch` | List local branches |
| `git branch -d <name>` | Delete a branch (only if merged) |
| `git merge main` | Bring `main`'s new commits into current branch |
| `git remote -v` | Confirm connection to GitHub |
| `git log --oneline -5` | See recent commit history |

---

## 8. PowerShell-specific gotchas (Windows)

- **No `touch`** — use `New-Item -ItemType File -Path filename`
- **No multi-arg `mkdir -p`** — use `New-Item -ItemType Directory -Path folder1, folder2`
- **Writing file content** — use a here-string:
  ```powershell
  @"
  line one
  line two
  "@ | Set-Content -Path filename
  ```
- **Placeholder paths in commands** (like `C:\path\to\...`) must be replaced with your real path — copy-pasting them literally will error with "path not found."

---

## 9. "How do I know it's actually in sync?" — troubleshooting

**A ZIP download is NOT a Git connection.** If your friend unzipped a downloaded copy of the repo instead of cloning it, his folder has no `.git` directory and will never sync, push, or pull — no matter what commands he runs. He must `git clone https://github.com/R3X06/coogaih_ver1.0.git` instead. Check with `git remote -v` — if that errors, it's not a real clone.

**Your push got rejected?** `main` is protected — direct pushes to `main` are blocked by design. Push to a branch instead, then open a PR (see §4).

**"Cannot find path" errors in PowerShell?** You're either not in the right folder (`cd` to your project first) or you copy-pasted a placeholder path without swapping in the real one.

**Not sure if a file made it to GitHub?** Check directly:
```powershell
git log -p -1 -- path/to/file
```
Shows the last commit that touched that file and its diff. Or just look at the file on github.com directly.

---

## 10. This project's specific rules (recap)

- `main` requires a PR + review, blocks force-push, blocks branch deletion.
- `.github/CODEOWNERS` requires **both of you** to approve any change to `docs/DATA_CONTRACT.md` or `docs/API_CONTRACT.md`.
- His folders: `focus-engine/`, `tests/`, `.github/workflows/` — don't touch these.
- Your folders: everything else (`backend/`, `frontend/`, extension code) — he shouldn't touch these.
- `.env` is gitignored — never commit real secrets, only `.env.example`.
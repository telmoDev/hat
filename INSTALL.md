# Installing the orchestrator (instructions for the agent)

You are an AI coding agent, Claude Code or Codex. A person gave you this repository's link and asked you to
install the orchestrator. Follow these steps in order. Speak to the person in their language, keep each
message short, and **ask before installing any software or changing anything outside the clone and the two
skill folders**. Never change git or gh configuration, never push, and never log in on the person's behalf.

## 1. Know where you are

Find out, without asking when you can check it yourself:

- **Your tool**: Claude Code or Codex (you know which one you are).
- **The other tool**: `command -v claude` and `command -v codex` (on Windows, `where claude` / `where codex`).
  Install for every tool the person has, unless they say otherwise.
- **The OS**: macOS, Linux or Windows (`uname -s`; on Windows `MINGW*`/`MSYS*` under Git Bash, or PowerShell).
- **Bash**. macOS and Linux have it. On Windows, every script runs in Git Bash: look for it with
  `where bash` or at `C:\Program Files\Git\bin\bash.exe`. If you run in PowerShell or cmd, call it with that
  full path: `& "C:\Program Files\Git\bin\bash.exe" -lc "<command>"`. If Git for Windows is missing, stop and
  ask the person to install it (`winget install --id Git.Git -e`), then continue.

## 2. Check the prerequisites

| Need | Check | If missing (ask first, or give the person the command) |
|---|---|---|
| git | `git --version` | macOS `xcode-select --install` · Linux `sudo apt install git` (or the distro's) · Windows `winget install --id Git.Git -e` |
| GitHub CLI | `gh --version` | macOS `brew install gh` · Linux https://github.com/cli/cli#installation · Windows `winget install --id GitHub.cli -e` |
| gh logged in | `gh auth status` | the person runs `gh auth login` themself (interactive). In Claude Code they can type `! gh auth login` |
| Python 3.8+ | `python3 --version` (Windows: `py -3 --version` or `python --version`) | macOS `brew install python` · Linux `sudo apt install python3` · Windows `winget install --id Python.Python.3.12 -e` |
| perl | `perl -v` | ships with macOS, Git Bash and most Linux; else the distro's package |
| jq (optional) | `jq --version` | not required: without it the hooks print plain text |

If the machine has **more than one GitHub account** in `gh auth status`, tell the person: the orchestrator's
push script can use a wrapper for the right account (`GIT_WRAPPER`, set up later per workspace).

## 3. Get the code

Install the **latest release**, not `main`. Clone to `~/orchestrator-setup` (on Windows,
`%USERPROFILE%\orchestrator-setup`) unless the person names another folder:

```bash
url=https://github.com/telmoDev/hat.git
tag=$(git ls-remote --tags --refs --sort=-v:refname "$url" 'v*' | head -1 | sed 's#.*refs/tags/##')
git clone --branch "$tag" "$url" ~/orchestrator-setup
```

If the folder already exists and is this repository (`git -C ~/orchestrator-setup remote get-url origin`),
update it instead: `git -C ~/orchestrator-setup fetch --tags`, find the latest tag as above, read the
`CHANGELOG.md` sections between the installed version (`VERSION`) and that tag, and tell the person what
changes. **Stop and wait for the person to accept the update.** Only after an explicit yes, run
`git -C ~/orchestrator-setup checkout <tag>`; without one, leave the installed version as it is. Bringing a
workspace up to date (its *Workspaces* lines) needs its own yes, workspace by workspace. If the folder is something else, ask the
person for another folder. Keep the clone: both tools read the skill from it.

## 4. Install the skill

From the clone, in bash (Git Bash on Windows):

```bash
bash install.sh --tools <claude|codex|claude,codex>
bash install.sh --tools <same> --check
```

`install.sh` links the clone as `~/.claude/skills/orchestrator-setup` (Claude Code) and
`~/.agents/skills/orchestrator-setup` (Codex): a symlink on macOS and Linux, a directory junction on
Windows (no admin rights needed). If it says a folder exists and is not a link, show the person the path
and ask before moving it. `--check` must print `ok` for each tool and each required prerequisite; fix
every `missing` line before you go on.

Then make sure the skill is visible. Claude Code: it appears as `orchestrator-setup` in a new session (and
usually in the current one). Codex: `$orchestrator-setup` or `/skills`; restart Codex if it isn't listed.

## 5. Tell the person how to work with it

Don't set up any workspace yet unless the person asks: that's the skill's job, run inside the workspace.
Read `USAGE.md` in the clone and tell the person, in at most 15 lines:

- what was installed (the version from `VERSION`), where the clone is, and for which tools;
- how to start: open their agent at the root of the folder that holds their repos and say
  "implementa la estructura de orquestador" (or "set up the orchestrator"); the skill asks a few
  questions and writes the files;
- the daily routine from `USAGE.md` (*Every session*), with the commands of their tool;
- how to update (ask the agent to update the orchestrator: it moves the clone to the latest release and
  says what changed) and uninstall (`bash install.sh --uninstall`);
- anything that is still missing (a login, a prerequisite) and who has to do it.

Then offer to set up a workspace now.

# Pushing this to your repo

I can't push for you — I have no credentials for your GitHub account, and I'm
not going to ask you for a token. These are the commands.

## 1. Fill in the placeholders

Three files reference `YOUR_GITHUB_USERNAME`, and `LICENSE` has `YOUR_NAME`.
From the repo root:

```bash
# Linux / macOS / WSL / Git Bash
sed -i 's/YOUR_GITHUB_USERNAME/yourhandle/g' README.md custom_components/myutilities/manifest.json
sed -i 's/YOUR_NAME/Your Name/' LICENSE
```

```powershell
# PowerShell
(Get-Content README.md) -replace 'YOUR_GITHUB_USERNAME','yourhandle' | Set-Content README.md
(Get-Content custom_components\myutilities\manifest.json) -replace 'YOUR_GITHUB_USERNAME','yourhandle' | Set-Content custom_components\myutilities\manifest.json
(Get-Content LICENSE) -replace 'YOUR_NAME','Your Name' | Set-Content LICENSE
```

HACS validation checks that `codeowners` in `manifest.json` is a real GitHub
handle, so this isn't cosmetic.

## 2. Check what you're about to commit

```bash
git status
git add -A
git status --short
```

Read that list before committing. `.gitignore` excludes `*.har` and
`myusage_dump/`, but confirm nothing from your captures is staged. The HAR
files you sent me have your old password in them — they must never reach a
public repo, and git history is not something you can quietly clean up later.

```bash
git diff --cached --stat        # what's changing
git ls-files --cached | grep -i har   # should print nothing
```

## 3. Commit and push

```bash
git commit -m "Rewrite against captured portal session

The sensor platform never loaded: SensorEntityDescription has been a frozen
dataclass since HA 2024.1, so subclassing it with a plain @dataclass raised
TypeError at import. Login also posted a third 'uc' field the portal rejects
with 'Invalid Session', and both login and fetch swallowed their errors and
returned zeros, so nothing surfaced.

Replaces the guessed endpoints with the real flow, adds a label-keyed parser
for the Prepaid summary page, imports the 30-day charge history into
long-term statistics, and adds diagnostics plus tests against a captured
page."

git push origin main
```

If your default branch is `master`, use that instead. `git branch --show-current`
will tell you.

## 4. Run the CI once

Check the **Actions** tab. Four jobs: hassfest, HACS, ruff, pytest. Fix
anything red before going further — that's what they're for.

`ruff` is likely to have opinions about formatting on first run. `ruff check
--fix .` locally handles most of it.

## 5. Cut a release

HACS falls back to your default branch if there's no release, which means
everyone tracks whatever you last pushed. Tag properly instead:

```bash
git tag -a v2.0.0 -m "v2.0.0"
git push origin v2.0.0
```

Then on GitHub: **Releases → Draft a new release**, pick the `v2.0.0` tag,
paste the 2.0.0 section of `CHANGELOG.md` as the body, publish. A tag alone
is not a release as far as HACS is concerned.

The version in `manifest.json` should match the tag. It's `2.0.0` already.

## 6. Still to do

- **`brands/icon.png`** — 256x256, transparent. HACS requires it. For the
  icon to show up *inside* Home Assistant you additionally need a PR to
  [home-assistant/brands](https://github.com/home-assistant/brands), which is
  a separate repo and a separate review.
- **Repo description and topics** on GitHub. Both are checked if you ever
  submit to the HACS default list. Suggested topics: `home-assistant`,
  `hacs`, `home-assistant-custom-component`, `myusage`, `utility`, `prepaid`.
- **Test it yourself for a week** before publicising it. The statistics
  import is the one piece I couldn't verify without a live recorder.
- **Issue template** asking for a diagnostics download. It'll save you a lot
  of back-and-forth with users on other utilities.

## Optional: let Claude Code do it

If you'd rather not run these by hand, Claude Code works in your local repo
with your own git credentials — you can hand it this file and have it do the
placeholder substitution, the safety check, and the commit.

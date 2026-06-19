# /sync — Dual-Repo Sync Command

Synchronize private `master` branch changes to the public `public` branch.

## Sub-Commands

### `/sync`
Full sync workflow: merge master → public → strip private files → push.

**Steps:**
1. Verify remotes exist (private + public)
2. `git checkout public`
3. `git merge master --no-ff -m "sync: merge master → public"`
4. Safety check: verify no private files on public branch (check whitelist.txt)
5. If private files leaked: `git rm --cached` them and commit
6. `git push public public`
7. `git checkout master`

**Private files to NEVER leak:**
- MEMORY.md
- plans/
- docs/blueprint.md
- .omo/
- kilo.json
- opencode.jsonc
- .python-version
- .codegraph/

### `/sync check`
Verify no private files on public branch.

**Steps:**
1. `git checkout public`
2. Check git ls-files against whitelist.txt inverse
3. Report any private files found
4. `git checkout master`

### `/sync status`
Show current sync state.

**Steps:**
1. Show remote URLs: `git remote -v`
2. Show branches: `git branch -a`
3. Show commits ahead/behind: `git log public..master --oneline`
4. Show current branch: `git branch --show-current`

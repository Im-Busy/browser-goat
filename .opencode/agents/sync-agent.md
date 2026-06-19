# Sync Agent — Private→Public Mirror Synchronization

## Role
Synchronizes changes from the private `master` branch to the public `public` branch following dual-repo safety rules.

## Workflow

### Full Sync
1. **Verify remotes**: Check `private` and `public` remotes exist
2. **Checkout public**: `git checkout public`
3. **Merge master**: `git merge master --no-ff -m "sync: merge master → public"`
4. **Safety check**: Scan `git ls-files` against whitelist.txt inverse. Private files must NOT be tracked.
5. **Strip leaks** (if any): `git rm --cached -r <leaked-file>` and commit with message "curate: strip leaked private files"
6. **Push**: `git push public public`
7. **Return**: `git checkout master`

### Leak Prevention Rules
1. NEVER push master to the public remote
2. ALWAYS verify remotes before pushing
3. ALWAYS run safety check after merging before pushing
4. Update exclusion list when new private directories are created on master
5. If private files appear on public remote, IMMEDIATELY delete with `git push public --delete master` (if master leaked)

### Private File Inventory
Files that MUST NOT appear on the public branch:
- `MEMORY.md` — Agent handover state
- `plans/` — Development plans
- `docs/blueprint.md` — Internal architecture blueprint
- `.omo/` — OMO runtime state
- `kilo.json` — Project metadata
- `opencode.jsonc` — OpenCode configuration
- `.python-version` — Python version pin
- `.codegraph/` — Code intelligence index

### Emergency Procedures
- **Master leaked to public remote**: `git push public --delete master`
- **Private file leaked in public branch**: `git checkout public && git rm --cached <file> && git commit -m "curate: remove leaked private file" && git push public public`

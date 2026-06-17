# Release process

`weatherlink-bridge` publishes to **PyPI** via `.github/workflows/release.yml` on a
published GitHub Release, using **PyPI Trusted Publishing (OIDC)** — no API
tokens. The multi-arch **Docker image** is built/pushed to `ghcr.io` separately
by `ci.yml` (the tag push that accompanies a Release triggers it).

## One-time setup (before the first release)

1. **PyPI pending publisher.** On pypi.org → *Your projects* → *Publishing* (or
   *Account → Publishing* for a project that doesn't exist yet), add a pending
   trusted publisher:
   - PyPI project name: `weatherlink-bridge`
   - Owner: `rodenj1`
   - Repository: `weatherlink-bridge`
   - Workflow filename: `release.yml`
   - Environment name: `pypi`
2. **GitHub Environment.** In the repo → *Settings → Environments* → create an
   environment named `pypi` (optionally add protection rules / required
   reviewers). The `publish-pypi` job references `environment: pypi`.
3. No secrets are required — OIDC handles authentication.

## Cutting a release

1. Bump the version in **both** places (they must agree; commitizen enforces it):
   - `pyproject.toml` → `[project] version`
   - `src/weatherlink_bridge/__init__.py` → `__version__`

   Either edit by hand, or use commitizen:
   ```bash
   uv run cz bump          # bumps per Conventional Commits, updates both files + CHANGELOG
   ```
2. Refresh the lock and commit:
   ```bash
   uv lock
   git add pyproject.toml src/weatherlink_bridge/__init__.py uv.lock CHANGELOG.md
   git commit -m "release: vX.Y.Z"
   git push
   ```
3. Create the GitHub Release with a matching tag:
   ```bash
   gh release create vX.Y.Z --title vX.Y.Z --notes "…"
   ```
   - Publishing the Release triggers `release.yml` → PyPI.
   - The tag push triggers `ci.yml` → multi-arch image to
     `ghcr.io/rodenj1/weatherlink-bridge:X.Y.Z` (and `:X.Y`).

## What the workflow enforces

- **`verify-version`** fails the run if the tag (minus `v`) ≠ `pyproject.toml`
  version, and refuses drafts and pre-releases.
- Full lint + type-check + test matrix (3.12, 3.13) must pass before build.
- `twine check --strict` and an artifact-version check gate the upload.
- After PyPI, the sdist + wheel are sigstore-signed and attached to the Release.

## Re-publishing a tag

If a run failed after `verify-version` but before publish, use the manual
trigger: *Actions → Release → Run workflow* with the existing tag (e.g.
`v0.1.0`). PyPI will reject a re-upload of an already-published version — bump
to a new version instead.

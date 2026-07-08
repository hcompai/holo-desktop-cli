# Releasing

`holo-desktop-cli` is published to [PyPI](https://pypi.org/project/holo-desktop-cli/) on every `v*` tag, via the [`publish.yml`](.github/workflows/publish.yml) GitHub Actions workflow. Authentication is OIDC (PyPI [Trusted Publishers](https://docs.pypi.org/trusted-publishers/)); no API tokens are stored as secrets.

## Runtime artifacts

The client downloads the pinned `hai-agent-runtime` binary on first run. Artifacts are published to an immutable, version-scoped CDN prefix (`https://assets.hcompanyprod.fr/hai-agent-runtime/<version>/hai-agent-runtime-<platform>.zip`) and are never overwritten, so a CDN edge can never serve stale bytes for an already-published version.

Bumping the pinned runtime is a two-field change in `src/holo_desktop/agent_client/runtime_install.py`: `PINNED_RUNTIME_VERSION` and the per-platform `sha256` digests in `MANIFEST` (the URL is derived from the version). H Company's runtime release pipeline builds the binary, uploads it under the versioned prefix, and opens the bump PR here; merging it and cutting a `v*` tag ships the new runtime with the next client release.

## One-time setup (PyPI side)

The first publish has to be bootstrapped because the PyPI project doesn't exist yet. Use a **Pending Publisher** so PyPI accepts the first OIDC request and auto-creates the project.

1. Sign in to https://pypi.org → Account settings → [Publishing](https://pypi.org/manage/account/publishing/).
2. Under **Add a new pending publisher**, fill in:
   - PyPI project name: `holo-desktop-cli`
   - Owner: `hcompai`
   - Repository: `holo-desktop-cli`
   - Workflow name: `publish.yml`
   - Environment: `release`
3. Repeat at https://test.pypi.org/manage/account/publishing/ if you also want TestPyPI dispatch runs to work. Use environment `testpypi` there.

## One-time setup (GitHub side)

The workflow references two [environments](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment) that gate the publish jobs:

1. Repo Settings → Environments → New environment → `release`. Optional but recommended: add a "Required reviewers" protection rule (you and one other maintainer).
2. New environment → `testpypi`. No protection rule needed.

## Cutting a release

```bash
git checkout main && git pull
# bump version in pyproject.toml (e.g. 0.0.1 -> 0.0.2)
git commit -am "release: 0.0.2"
git tag v0.0.2
git push origin main --tags
```

The workflow then:
1. Builds wheel + sdist with `uv build`.
2. Asserts the git tag matches `project.version` in `pyproject.toml` (cheap safety net).
3. Publishes to PyPI via OIDC (gated by the `release` environment). Sigstore [attestations](https://docs.pypi.org/attestations/) are generated automatically.
4. Creates a GitHub Release with auto-generated notes and attaches the Python artifacts plus installer assets.

Don't forget to land a `CHANGELOG.md` entry as part of the version-bump commit.

## Installer assets

Every GitHub Release includes:

- `install.sh`
- `install.ps1`
- `manifest.json`

The installer uses the `holo-desktop-cli` PyPI version declared in `install/manifest.json`, plus the manifest-pinned `uv` artifacts and SHA256 values. The public installer CDN must update only after PyPI publish succeeds; otherwise the public installer could point users at a package version that is not installable yet.

After `publish-pypi` succeeds, the `release` job creates the GitHub Release and the `publish-installer-cdn` job uploads:

- `install/install.sh` -> `s3://hcompany-holo-desktop-installer-assets/install.sh`
- `install/install.ps1` -> `s3://hcompany-holo-desktop-installer-assets/install.ps1`
- `install/manifest.json` -> `s3://hcompany-holo-desktop-installer-assets/install/manifest.json`

Verify:

```bash
curl -fsSL https://install.holo.ai/install.sh | head
curl -fsSL https://install.holo.ai/install.ps1 | head
curl -fsSL https://install.holo.ai/install/manifest.json | python -m json.tool
```

Rollback is a new patch release that restores the previous manifest and installer scripts. If a same-version emergency rollback is required, manually upload the previous three assets to the same S3 keys and verify the CDN endpoints after the 300-second cache window.

## Dry-run on TestPyPI

`workflow_dispatch` → choose `testpypi` → runs the build + uploads to https://test.pypi.org/project/holo-desktop-cli/ without touching prod. Useful for testing workflow changes; not gated on runtime artifacts.

## If publish fails

- **`HTTPError: 403 Forbidden` from PyPI**: the Trusted Publisher is mis-configured. Re-check workflow filename, environment, owner, repo on the PyPI publishing page.
- **`File already exists`**: the version was already published. PyPI does not allow re-uploading the same version; bump `pyproject.toml` and tag again.
- **Tag/version mismatch (workflow step fails early)**: tag and `project.version` disagree. Re-tag after bumping `pyproject.toml`.

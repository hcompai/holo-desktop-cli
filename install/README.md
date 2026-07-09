# Installer Assets

The release workflow attaches these files to every GitHub Release:

- `install.sh`
- `install.ps1`
- `manifest.json`

## Publish To The Public Asset CDN

The `publish-installer-cdn` release job uploads these files after PyPI publish
and GitHub Release creation:

- `install/install.sh` -> `s3://hcompany-holo-desktop-installer-assets/install.sh`
- `install/install.ps1` -> `s3://hcompany-holo-desktop-installer-assets/install.ps1`
- `install/manifest.json` -> `s3://hcompany-holo-desktop-installer-assets/install/manifest.json`

Verify:

```bash
curl -fsSL https://install.hcompany.ai/install.sh | head
curl -fsSL https://install.hcompany.ai/install.ps1 | head
curl -fsSL https://install.hcompany.ai/install/manifest.json | python -m json.tool
```

## Rollback

Cut a new patch release that restores the previous release's installer files.
For a same-version emergency rollback, manually upload the previous files to the
same S3 keys and verify the CDN endpoints after the 300-second cache window. The
installer manifest pins both the `holo-desktop-cli` PyPI version and the `uv`
artifact checksums, so reverting the manifest restores the previous install
target.

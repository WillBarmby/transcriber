# Releasing tranpro

Releases are built by GitHub Actions from the repository and published with
PyPI Trusted Publishing. No long-lived PyPI token belongs in GitHub secrets.

## One-time setup

Create pending Trusted Publishers on PyPI and TestPyPI with these values:

| Setting | Value |
| --- | --- |
| PyPI project | `tranpro` |
| GitHub owner | `WillBarmby` |
| Repository | `transcriber` |
| Workflow | `release.yml` |
| Environment | `pypi` on PyPI; `testpypi` on TestPyPI |

Create matching `pypi` and `testpypi` environments in the GitHub repository.
The environments may require approval if an extra release confirmation is
desired.

## Rehearse on TestPyPI

1. Update the version in `pyproject.toml` and the entry in `CHANGELOG.md`.
2. Merge the release preparation pull request into `main`.
3. Run the **Release** workflow manually from the `main` branch.
4. Inspect the TestPyPI project and download its wheel artifact.

The manual workflow publishes only to TestPyPI. Re-running the same version is
safe: an already uploaded file is skipped.

## Publish to PyPI

After the TestPyPI rehearsal succeeds, tag the exact tested commit and push the
tag:

```shell
git switch main
git pull --ff-only
git tag v0.1.0a1
git push origin v0.1.0a1
```

A `v*` tag makes the workflow rebuild the distributions, verify a clean wheel
installation, publish to PyPI, and create a GitHub release containing the wheel
and source distribution. The tag version must match the package version without
the leading `v`.

Finally, verify the public installation in a fresh virtual environment:

```shell
python3 -m venv /tmp/tranpro-release-check
/tmp/tranpro-release-check/bin/python -m pip install 'tranpro[local]'
/tmp/tranpro-release-check/bin/tp --version
```

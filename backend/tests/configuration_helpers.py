"""Integration test client that edits a freshly read configuration revision."""


def patch_current(client, path, *, json):
    fetched = client.get(path)
    assert fetched.status_code == 200, fetched.text
    current = fetched.json()
    if path.startswith("/api/model-connections/"):
        revisions = {
            "expected_config_revision": current["config_revision"],
            "expected_credential_revision": current["credential_revision"],
        }
    else:
        revisions = {"expected_revision": current["revision"]}
    return client.patch(path, json={**revisions, **json})


def set_submission_limits(commands, **changes):
    from dataclasses import replace

    settings = replace(commands.settings, **changes)
    commands.settings = settings
    commands.runs.settings = settings
    commands.runs.configuration.settings = settings

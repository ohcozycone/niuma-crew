"""Integration test client that edits a freshly read configuration revision."""


def patch_current(client, path, *, json):
    current = client.get(path).json()
    if path.startswith("/api/model-connections/"):
        revisions = {
            "expected_config_revision": current.get("config_revision", 1),
            "expected_credential_revision": current.get("credential_revision", 1),
        }
    else:
        revisions = {"expected_revision": current.get("revision", 1)}
    return client.patch(path, json={**revisions, **json})


def set_submission_limits(commands, **changes):
    from dataclasses import replace

    settings = replace(commands.settings, **changes)
    commands.settings = settings
    commands.admission.settings = settings
    commands.assembler.settings = settings

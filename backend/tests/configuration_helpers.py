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
    from dataclasses import fields, replace

    configuration = commands.runs.configuration
    engine_fields = {field.name for field in fields(configuration.agent)}
    configuration.agent = replace(
        configuration.agent, **{k: v for k, v in changes.items() if k in engine_fields}
    )
    settings = replace(
        commands.settings, **{k: v for k, v in changes.items() if k not in engine_fields}
    )
    commands.settings = settings
    commands.runs.settings = settings
    configuration.settings = settings

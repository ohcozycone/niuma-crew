from deepagents.backends.protocol import (
    ExecuteResponse,
)
from langchain_opensandbox import OpenSandboxBackend

from app.environments.open_sandbox import OpenSandboxOperations


class SandboxFileBackend(OpenSandboxBackend):
    def __init__(self, *, sandbox, timeout=60):
        super().__init__(sandbox=sandbox, timeout=timeout)
        self.operations = OpenSandboxOperations(sandbox, timeout)

    def execute(self, command, *, timeout=None):
        result = self.operations.execute(command, timeout=timeout)
        return ExecuteResponse(output=result.output, exit_code=result.exit_code)

    def materialize_readonly(self, files):
        self.operations.materialize_readonly(files)

    def check_path(self, path, *, write=False):
        self.operations.check_path(path, write=write)

    def collect_outputs(self):
        return self.operations.collect_outputs()

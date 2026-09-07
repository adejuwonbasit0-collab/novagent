from pydantic import BaseModel, Field

from app.models.permission import PermissionScope, RiskLevel
from app.services.connection_manager import CommandTimeout, DeviceNotConnected, connection_manager
from app.tools.base import BaseTool, ToolExecutionContext, ToolResponse, ToolResult, ToolRegistry


async def dispatch(tool_name: str, params: dict, ctx: ToolExecutionContext) -> ToolResponse:
    if ctx.device_id is None:
        return ToolResponse(result=ToolResult.FAILURE, error="This action requires a connected desktop agent.")
    try:
        result = await connection_manager.send_command(ctx.device_id, tool_name, params, timeout=20)
    except DeviceNotConnected:
        return ToolResponse(result=ToolResult.FAILURE, error="The desktop agent is not connected.")
    except CommandTimeout:
        return ToolResponse(result=ToolResult.FAILURE, error="The desktop agent did not respond in time.")
    if result.get("success"):
        return ToolResponse(result=ToolResult.SUCCESS, message=result.get("message"), data={"resource": tool_name})
    return ToolResponse(result=ToolResult.FAILURE, error=result.get("error") or "The desktop agent reported failure")


class CreateFolderInput(BaseModel):
    path: str = Field(description="Full path for the folder to create")


class CreateFolderTool(BaseTool):
    name = "create_folder"
    description = "Create a folder on the connected computer."
    input_schema = CreateFolderInput
    required_permission = PermissionScope.FILES_WRITE
    risk_level = RiskLevel.MEDIUM
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: CreateFolderInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


class CreateFileInput(BaseModel):
    path: str = Field(description="Full path for the file to create")
    content: str = Field(default="", max_length=50000, description="Text content to write into the new file, if any")


class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Create a new file (optionally with text content) on the connected computer. Fails if a file already exists at that path -- use a different name rather than overwriting."
    input_schema = CreateFileInput
    required_permission = PermissionScope.FILES_WRITE
    risk_level = RiskLevel.MEDIUM
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: CreateFileInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


class TypeTextInput(BaseModel):
    text: str = Field(max_length=10000, description="Text to type into the currently focused application")


class TypeTextTool(BaseTool):
    name = "type_text"
    description = "Type text into the currently focused application on the connected computer."
    input_schema = TypeTextInput
    required_permission = PermissionScope.FILES_WRITE
    risk_level = RiskLevel.MEDIUM
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: TypeTextInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


class OpenFolderInApplicationInput(BaseModel):
    path: str
    app_name: str


class OpenFolderInApplicationTool(BaseTool):
    name = "open_folder_in_application"
    description = "Open a folder in a named application such as Visual Studio Code."
    input_schema = OpenFolderInApplicationInput
    required_permission = PermissionScope.APP_OPEN
    risk_level = RiskLevel.LOW
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: OpenFolderInApplicationInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


ToolRegistry.register(CreateFolderTool())
ToolRegistry.register(CreateFileTool())
ToolRegistry.register(TypeTextTool())
ToolRegistry.register(OpenFolderInApplicationTool())
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


# MISSING FEATURE, now added — see the matching comment in
# desktop-agent/os_control/base.py. Neither of spec sections 13-14's
# headline examples ("what app am I using?", "review the code I'm working
# on") had a tool to call at all.
class GetActiveWindowInput(BaseModel):
    pass


class GetActiveWindowTool(BaseTool):
    name = "get_active_window"
    description = (
        "Get the name and window title of whatever application currently has focus on the "
        "user's connected computer. Use this to answer 'what app am I using?' or to figure out "
        "which application a follow-up request (like 'review my code') is about."
    )
    input_schema = GetActiveWindowInput
    # SCREEN_READ, not APP_OPEN -- a window title can contain sensitive
    # content (an open document's filename, a private browser tab's page
    # title), so this is gated behind the same higher-friction permission
    # as spec section 31's "See what's on a connected device's screen",
    # not the low-friction "open an app" permission.
    required_permission = PermissionScope.SCREEN_READ
    risk_level = RiskLevel.LOW
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: GetActiveWindowInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, {}, ctx)


class ReadFileInput(BaseModel):
    path: str = Field(description="Full path of the file to read")
    max_chars: int = Field(default=20000, le=20000, description="Maximum characters to read back")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Read the text content of a file on the connected computer (e.g. a source code file the "
        "user is asking about). Truncated for very large files -- ask the user to point at a "
        "narrower file or section if what you need isn't in the truncated portion."
    )
    input_schema = ReadFileInput
    required_permission = PermissionScope.FILES_READ
    risk_level = RiskLevel.LOW
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: ReadFileInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


class RenameFileInput(BaseModel):
    old_path: str = Field(description="Current full path of the file or folder")
    new_path: str = Field(description="New full path or name for the file or folder")


class RenameFileTool(BaseTool):
    name = "rename_file"
    description = "Rename a file or folder on the connected computer."
    input_schema = RenameFileInput
    required_permission = PermissionScope.FILES_WRITE
    risk_level = RiskLevel.MEDIUM
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: RenameFileInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


class DeleteFileInput(BaseModel):
    path: str = Field(description="Full path of the file to permanently delete")


class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = "Permanently delete a file on the connected computer. Always requires explicit confirmation."
    input_schema = DeleteFileInput
    required_permission = PermissionScope.FILES_WRITE
    risk_level = RiskLevel.HIGH
    requires_confirmation = True
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: DeleteFileInput, ctx: ToolExecutionContext) -> ToolResponse:
        return await dispatch(self.name, params.model_dump(), ctx)


ToolRegistry.register(GetActiveWindowTool())
ToolRegistry.register(ReadFileTool())
ToolRegistry.register(RenameFileTool())
ToolRegistry.register(DeleteFileTool())
from pydantic import BaseModel, Field

from app.models.permission import PermissionScope, RiskLevel
from app.services.knowledge_retrieval import search_knowledge
from app.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResponse, ToolResult


class SearchKnowledgeInput(BaseModel):
    query: str = Field(description="What to search for in the user's uploaded documents/notes")


class SearchKnowledgeTool(BaseTool):
    name = "search_knowledge"
    description = (
        "Search the user's own uploaded documents and notes (their personal knowledge base) for "
        "content relevant to a question. Use this when the user asks about something that sounds "
        "like it would be in a document they've uploaded (e.g. 'what does my lease say about X', "
        "'check my notes on Y') rather than general knowledge or something requiring the internet. "
        "This is keyword-based search, not general knowledge -- if it returns nothing, that means "
        "the user hasn't uploaded anything covering that topic, not that the answer doesn't exist."
    )
    input_schema = SearchKnowledgeInput
    # A dedicated scope, not FILES_READ -- FILES_READ means "read files on
    # a connected device" (see os_file_tools.py's ReadFileTool and the
    # dashboard's permission description for it); this is reading the
    # user's own already-uploaded knowledge base entries out of the
    # backend's own database, nothing to do with a device at all. Reusing
    # FILES_READ would show the user a misleading permission description
    # ("read files on connected devices") for a request that has nothing
    # to do with their computer.
    required_permission = PermissionScope.KNOWLEDGE_READ
    risk_level = RiskLevel.LOW
    supported_platforms = ("windows", "macos", "linux")

    async def _run(self, params: SearchKnowledgeInput, ctx: ToolExecutionContext) -> ToolResponse:
        matches = await search_knowledge(ctx.db, ctx.user.id, params.query)
        if not matches:
            return ToolResponse(
                result=ToolResult.SUCCESS,
                message="No matching content found in the user's knowledge base for that query.",
            )
        combined = "\n\n---\n\n".join(m["content"] for m in matches)
        return ToolResponse(result=ToolResult.SUCCESS, message=combined, data={"match_count": len(matches)})


ToolRegistry.register(SearchKnowledgeTool())

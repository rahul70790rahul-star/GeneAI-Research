"""GeneAI Biotechnology Research Assistant - Phase 5.1."""
from __future__ import annotations

from geneai.biotech_assistant.core import (
    BiotechAssistant,
    create_biotech_assistant,
    QuestionType,
    EvidenceGrade,
    Answer,
    Citation,
    ConversationTurn,
    ConversationMemory,
    ToolCall,
)
from geneai.biotech_assistant.tool_wrappers import (
    ToolRegistry,
    get_tool_registry,
    get_tool,
)
from geneai.biotech_assistant.prompts import (
    SYSTEM_PROMPT,
    QUESTION_CLASSIFICATION_PROMPT,
    TOOL_SELECTION_PROMPT,
    ANSWER_SYNTHESIS_PROMPT,
    get_question_type_prompt,
)
from geneai.biotech_assistant.memory import (
    ConversationMemory as MemoryConversationMemory,
    MemoryStore,
    get_memory_store,
    get_current_memory,
    new_conversation,
)
from geneai.biotech_assistant.citations import (
    Citation as CitationsCitation,
    CitationManager,
    SourceType,
    EvidenceGrade as CitationsEvidenceGrade,
    create_citation_from_pubmed,
    create_citation_from_database,
    create_citation_from_computation,
)
from geneai.biotech_assistant.ui import (
    render_biotech_assistant,
    render_assistant_dashboard,
    render as render_assistant,
)

__all__ = [
    # Core
    "BiotechAssistant",
    "create_biotech_assistant",
    "QuestionType",
    "EvidenceGrade",
    "Answer",
    "Citation",
    "ConversationTurn",
    "ConversationMemory",
    "ToolCall",
    # Tool wrappers
    "ToolRegistry",
    "get_tool_registry",
    "get_tool",
    # Prompts
    "SYSTEM_PROMPT",
    "QUESTION_CLASSIFICATION_PROMPT",
    "TOOL_SELECTION_PROMPT",
    "ANSWER_SYNTHESIS_PROMPT",
    "get_question_type_prompt",
    # Memory
    "MemoryConversationMemory",
    "MemoryStore",
    "get_memory_store",
    "get_current_memory",
    "new_conversation",
    # Citations
    "CitationsCitation",
    "CitationManager",
    "SourceType",
    "CitationsEvidenceGrade",
    "create_citation_from_pubmed",
    "create_citation_from_database",
    "create_citation_from_computation",
    # UI
    "render_biotech_assistant",
    "render_assistant_dashboard",
    "render_assistant",
]

__version__ = "5.1.0"
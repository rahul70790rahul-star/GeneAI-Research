"""Tool registry and base tool class for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """Tool parameter specification."""
    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = False
    default: Any = None
    enum: list[Any] | None = None


@dataclass
class ToolSpec:
    """Tool specification."""
    name: str
    description: str
    category: str
    parameters: list[ToolParameter] = field(default_factory=list)
    requires_approval: bool = False
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)


class Tool(ABC):
    """Base class for all tools."""

    def __init__(self, spec: ToolSpec):
        self.spec = spec
        self.logger = logging.getLogger(__name__)

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def description(self) -> str:
        return self.spec.description

    @property
    def category(self) -> str:
        return self.spec.category

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                p.name: {
                    "type": p.type,
                    "description": p.description,
                    "enum": p.enum,
                    "default": p.default,
                }
                for p in self.spec.parameters
            },
            "required": [p.name for p in self.spec.parameters if p.required],
        }

    @property
    def requires_approval(self) -> bool:
        return self.spec.requires_approval

    @abstractmethod
    def execute(self, **kwargs) -> dict[str, Any]:
        """Execute the tool with given parameters."""
        pass

    def validate_parameters(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate parameters against schema."""
        required = [p.name for p in self.spec.parameters if p.required]
        for req in required:
            if req not in params:
                return False, f"Missing required parameter: {req}"

        for param in self.spec.parameters:
            if param.name in params:
                value = params[param.name]
                if param.enum and value not in param.enum:
                    return False, f"Invalid value for {param.name}: must be one of {param.enum}"

        return True, None


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self.categories: dict[str, list[str]] = {}
        self.logger = logging.getLogger(__name__)

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool
        if tool.category not in self.categories:
            self.categories[tool.category] = []
        self.categories[tool.category].append(tool.name)
        self.logger.info("Registered tool: %s (%s)", tool.name, tool.category)

    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self.tools:
            tool = self.tools.pop(name)
            if tool.category in self.categories:
                self.categories[tool.category].remove(name)
            self.logger.info("Unregistered tool: %s", name)
            return True
        return False

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self.tools.get(name)

    def list_tools(self, category: str | None = None) -> list[Tool]:
        """List all tools, optionally filtered by category."""
        if category:
            return [self.tools[name] for name in self.categories.get(category, [])]
        return list(self.tools.values())

    def get_categories(self) -> list[str]:
        """Get all tool categories."""
        return list(self.categories.keys())

    def search(self, query: str) -> list[Tool]:
        """Search tools by name or description."""
        query = query.lower()
        results = []
        for tool in self.tools.values():
            if query in tool.name.lower() or query in tool.description.lower():
                results.append(tool)
        return results


# Global registry instance
tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return tool_registry
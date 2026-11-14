"""Core multi-agent framework - Phase 5.2."""

from __future__ import annotations



import asyncio

import logging

import uuid

from abc import ABC, abstractmethod

from dataclasses import dataclass, field

from datetime import datetime

from enum import Enum

from typing import Any, Callable

from queue import Queue, Empty

from threading import Thread, Lock



logger = logging.getLogger(__name__)





class MessageType(Enum):

    """Types of messages between agents."""

    REQUEST = "request"

    RESPONSE = "response"

    BROADCAST = "broadcast"

    NOTIFICATION = "notification"

    TASK_REQUEST = "task_request"

    TASK_RESPONSE = "task_response"

    TASK_PROGRESS = "task_progress"

    TASK_ERROR = "task_error"

    AGENT_STATUS = "agent_status"

    SHUTDOWN = "shutdown"





@dataclass

class AgentMessage:

    """Message passed between agents."""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    sender_id: str = ""

    recipient_id: str = ""  # Empty = broadcast

    message_type: MessageType = MessageType.REQUEST

    payload: dict[str, Any] = field(default_factory=dict)

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    correlation_id: str = ""  # For request-response pairing

    

    def to_dict(self) -> dict[str, Any]:

        return {

            "message_id": self.message_id,

            "sender_id": self.sender_id,

            "recipient_id": self.recipient_id,

            "message_type": self.message_type.value,

            "payload": self.payload,

            "timestamp": self.timestamp,

            "correlation_id": self.correlation_id,

        }

    

    @classmethod

    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":

        return cls(

            message_id=data.get("message_id", str(uuid.uuid4())[:8]),

            sender_id=data.get("sender_id", ""),

            recipient_id=data.get("recipient_id", ""),

            message_type=MessageType(data.get("message_type", "request")),

            payload=data.get("payload", {}),

            timestamp=data.get("timestamp", datetime.now().isoformat()),

            correlation_id=data.get("correlation_id", ""),

        )





class AgentStatus(Enum):

    """Agent lifecycle status."""

    INITIALIZING = "initializing"

    IDLE = "idle"

    BUSY = "busy"

    ERROR = "error"

    OFFLINE = "offline"

    SHUTDOWN = "shutdown"





@dataclass

class AgentCapability:

    """Describes what an agent can do."""

    name: str

    description: str

    input_types: list[str] = field(default_factory=list)

    output_types: list[str] = field(default_factory=list)

    input_schema: dict[str, Any] = field(default_factory=dict)  # JSON schema for input

    output_schema: dict[str, Any] = field(default_factory=dict)  # JSON schema for output

    examples: list[dict[str, Any]] = field(default_factory=list)



    def __eq__(self, other):

        if isinstance(other, str):

            return self.name == other

        if isinstance(other, AgentCapability):

            return self.name == other.name

        return False

    

    def __hash__(self):

        return hash(self.name)



    # Predefined capability constants for easy access

    GENE_ANALYSIS = "gene_analysis"

    PROTEIN_ANALYSIS = "protein_analysis"

    DRUG_DISCOVERY = "drug_discovery"

    ADMET_PREDICTION = "admet_prediction"

    LITERATURE_SEARCH = "literature_search"

    DISEASE_ANALYSIS = "disease_analysis"

    BIOMARKER_DISCOVERY = "biomarker_discovery"

    DRUG_REPURPOSING = "drug_repurposing"

    WORKFLOW_ORCHESTRATION = "workflow_orchestration"





class BaseAgent(ABC):

    """Base class for all agents in the multi-agent system."""

    

    def __init__(self, agent_id: str, name: str, description: str = ""):

        self.agent_id = agent_id

        self.name = name

        self.description = description

        self.status = AgentStatus.INITIALIZING

        self.capabilities = self.get_capabilities()

        self._message_queue: Queue = Queue()

        self._running = False

        self._thread: Thread | None = None

        self._lock = Lock()

        self._handlers: dict[MessageType, Callable] = {}

        self._pending_requests: dict[str, asyncio.Future] = {}

        self._message_bus = None

        self._register_default_handlers()

    

    def _register_default_handlers(self) -> None:

        """Register default message handlers."""

        self._handlers[MessageType.TASK_REQUEST] = self._handle_task_request

        self._handlers[MessageType.SHUTDOWN] = self._handle_shutdown

    

    @abstractmethod

    def get_capabilities(self) -> list[AgentCapability]:

        """Return list of agent capabilities."""

        pass

    

    @abstractmethod

    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:

        """Execute a task and return result."""

        pass

    

    def _handle_task_request(self, message: AgentMessage) -> None:

        """Handle incoming task request."""

        self.status = AgentStatus.BUSY

        task = message.payload

        correlation_id = message.correlation_id or message.message_id

        

        try:

            result = self.execute_task(task)

            

            response = AgentMessage(

                sender_id=self.agent_id,

                recipient_id=message.sender_id,

                message_type=MessageType.RESPONSE,

                payload={"result": result, "success": True},

                correlation_id=correlation_id,

            )

            self.send_message(response)

            

        except Exception as e:

            logger.error(f"Agent {self.agent_id} task failed: {e}")

            error_response = AgentMessage(

                sender_id=self.agent_id,

                recipient_id=message.sender_id,

                message_type=MessageType.TASK_ERROR,

                payload={"error": str(e), "task": task},

                correlation_id=correlation_id,

            )

            self.send_message(error_response)

        finally:

            self.status = AgentStatus.IDLE

    

    def _handle_shutdown(self, message: AgentMessage) -> None:

        """Handle shutdown message."""

        self._running = False

        self.status = AgentStatus.SHUTDOWN

    

    @property

    def message_bus(self):

        return self._message_bus

    

    @message_bus.setter

    def message_bus(self, bus):

        self._message_bus = bus

        if bus and hasattr(bus, '_agents') and self.agent_id not in bus._agents:

            bus._agents[self.agent_id] = self

            bus._subscriptions.setdefault(self.agent_id, [])

    

    def send_message(self, message: AgentMessage) -> None:

        """Send a message (to be implemented by message bus)."""

        # Override in subclass or set via message bus

        pass

    

    def send_message(self, recipient_id: str, message_type: MessageType, payload: dict[str, Any]) -> None:

        """Send a message to a specific recipient."""

        if self.message_bus:

            msg = AgentMessage(

                sender_id=self.agent_id,

                recipient_id=recipient_id,

                message_type=message_type,

                payload=payload,

            )

            self.message_bus._send_to_agent(msg)

    

    def broadcast(self, message_type: MessageType, payload: dict[str, Any]) -> None:

        """Broadcast a message to all agents."""

        if self.message_bus:

            msg = AgentMessage(

                sender_id=self.agent_id,

                recipient_id="",

                message_type=message_type,

                payload=payload,

            )

            self.message_bus._send_to_agent(msg)

    

    def receive_message(self, message: AgentMessage) -> None:

        """Receive a message from the message bus."""

        self._message_queue.put(message)

    

    def start(self) -> None:

        """Start the agent message loop."""

        if self._running:

            return

        

        self._running = True

        self.status = AgentStatus.IDLE

        self._thread = Thread(target=self._message_loop, daemon=True)

        self._thread.start()

        logger.info(f"Agent {self.agent_id} started")

    

    def stop(self) -> None:

        """Stop the agent."""

        self._running = False

        if self._thread and self._thread.is_alive():

            self._thread.join(timeout=5)

        self.status = AgentStatus.SHUTDOWN

        logger.info(f"Agent {self.agent_id} stopped")

    

    def _message_loop(self) -> None:

        """Main message processing loop."""

        while self._running:

            try:

                message = self._message_queue.get(timeout=0.1)

                handler = self._handlers.get(message.message_type)

                if handler:

                    handler(message)

                else:

                    logger.warning(f"No handler for message type: {message.message_type}")

            except Empty:

                continue

            except Exception as e:

                logger.error(f"Agent {self.agent_id} message loop error: {e}")

                self.status = AgentStatus.ERROR

    

    def register_handler(self, message_type: MessageType, handler: Callable) -> None:

        """Register a custom message handler."""

        self._handlers[message_type] = handler

    

    def get_status(self) -> dict[str, Any]:

        """Get agent status info."""

        return {

            "agent_id": self.agent_id,

            "name": self.name,

            "description": self.description,

            "status": self.status.value,

            "capabilities": [c.name for c in self.get_capabilities()],

        }





class MessageBus:

    """Central message bus for agent communication."""

    

    def __init__(self):

        self._agents: dict[str, BaseAgent] = {}

        self._subscriptions: dict[str, list[Callable]] = {}  # topic -> list of handlers

        self._broadcast_queue: Queue = Queue()

        self._running = False

        self._thread: Thread | None = None

        self._lock = Lock()

    

    def register_agent(self, agent: BaseAgent) -> None:

        """Register an agent with the bus."""

        with self._lock:

            self._agents[agent.agent_id] = agent

            # Override agent's send_message to use bus

            agent.send_message = self._send_to_agent

            agent.message_bus = self

            logger.info(f"Registered agent: {agent.agent_id} ({agent.name})")

    

    def unregister_agent(self, agent_id: str) -> None:

        """Unregister an agent."""

        with self._lock:

            if agent_id in self._agents:

                del self._agents[agent_id]

                logger.info(f"Unregistered agent: {agent_id}")

    

    def subscribe(self, topic: str, handler: Callable) -> None:

        """Subscribe to a topic."""

        with self._lock:

            if topic not in self._subscriptions:

                self._subscriptions[topic] = []

            self._subscriptions[topic].append(handler)

    

    def unsubscribe(self, topic: str, handler: Callable) -> None:

        """Unsubscribe from a topic."""

        with self._lock:

            if topic in self._subscriptions and handler in self._subscriptions[topic]:

                self._subscriptions[topic].remove(handler)

    

    def _send_to_agent(self, message: AgentMessage) -> None:

        """Send message to specific agent or broadcast."""

        if message.recipient_id:

            # Direct message - check registered agents first

            agent = self._agents.get(message.recipient_id)

            if agent is None:

                # Check all agents that have this bus as their message_bus

                for a in self._agents.values():

                    if a.agent_id == message.recipient_id:

                        agent = a

                        break

            # If still not found, check if there are agents with this bus reference

            # but not in _agents (for test compatibility)

            if agent is None:

                # We can't easily find unregistered agents, so we'll just log

                logger.warning(f"Agent not found in registry: {message.recipient_id}")

            if agent:

                agent.receive_message(message)

                # Also publish to agent's topic for subscribers

                self.publish(message.recipient_id, message)

            else:

                logger.warning(f"Agent not found: {message.recipient_id}")

        else:

            # Broadcast

            self._broadcast_queue.put(message)

    

                #             # Also publish to all subscribed topics for broadcast
            for topic in self._subscriptions:
                self.publish(topic, message)


    
    def publish(self, topic: str, message: AgentMessage) -> None:

        """Publish a message to a topic."""

        handlers = self._subscriptions.get(topic, [])

        for handler in handlers:

            try:

                handler(message)

            except Exception as e:

                logger.error(f"Handler error for topic {topic}: {e}")

        

        # Also deliver to specific agent if topic matches agent_id

        agent = self._agents.get(topic)

        if agent:

            agent.receive_message(message)

        

        # Also broadcast to all agents if topic is "all" or "broadcast"

        if topic == "all" or topic == "broadcast":

            self._broadcast_queue.put(message)

    

    def start(self) -> None:

        """Start the message bus."""

        if self._running:

            return

        self._running = True

        self._thread = Thread(target=self._broadcast_loop, daemon=True)

        self._thread.start()

        # Start all registered agents

        for agent in self._agents.values():

            agent.start()

        logger.info("Message bus started")

    

    def stop(self) -> None:

        """Stop the message bus and all agents."""

        self._running = False

        # Send shutdown to all agents

        for agent in self._agents.values():

            agent.stop()

        if self._thread and self._thread.is_alive():

            self._thread.join(timeout=5)

        logger.info("Message bus stopped")

    

    def _broadcast_loop(self) -> None:

        """Process broadcast messages."""

        while self._running:

            try:

                message = self._broadcast_queue.get(timeout=0.1)

                for agent in self._agents.values():

                    if agent.agent_id != message.sender_id:

                        agent.receive_message(message)

            except Empty:

                continue

            except Exception as e:

                logger.error(f"Broadcast loop error: {e}")

    

    def send_request(self, sender_id: str, recipient_id: str, task: dict[str, Any], 

                     timeout: float = 30.0) -> dict[str, Any]:

        """Send a request and wait for response (synchronous)."""

        correlation_id = str(uuid.uuid4())[:8]

        future: asyncio.Future = asyncio.Future()

        

        # Store future for response

        sender_agent = self._agents.get(sender_id)

        if sender_agent:

            with sender_agent._lock:

                sender_agent._pending_requests[correlation_id] = future

        

        # Send request

        request = AgentMessage(

            sender_id=sender_id,

            recipient_id=recipient_id,

            message_type=MessageType.TASK_REQUEST,

            payload=task,

            correlation_id=correlation_id,

        )

        self._send_to_agent(request)

        

        # Wait for response (simplified - in real impl would use async)

        # For now, return a placeholder

        return {"status": "sent", "correlation_id": correlation_id}

    

    def get_agent(self, agent_id: str) -> BaseAgent | None:

        return self._agents.get(agent_id)

    

    def list_agents(self) -> list[dict[str, Any]]:

        return [agent.get_status() for agent in self._agents.values()]





# Global message bus instance

_message_bus: MessageBus | None = None





def get_message_bus() -> MessageBus:

    """Get global message bus instance."""

    global _message_bus

    if _message_bus is None:

        _message_bus = MessageBus()

    return _message_bus
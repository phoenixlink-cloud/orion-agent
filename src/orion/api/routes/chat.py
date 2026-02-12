# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Orion Agent -- Chat Routes (REST + WebSocket)."""

import contextlib

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from orion.api._shared import ChatRequest, _get_orion_log

router = APIRouter()


@router.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """REST endpoint for chat (non-streaming)."""
    if not request.message:
        raise HTTPException(status_code=400, detail="No message provided")
    if not request.workspace:
        raise HTTPException(status_code=400, detail="No workspace specified")

    try:
        from orion.core.agents.router import RequestRouter

        router_inst = RequestRouter(
            request.workspace,
            stream_output=False,
            sandbox_enabled=False,
        )
        result = await router_inst.handle_request(request.message)
        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "route": result.get("route", "unknown"),
            "actions": result.get("actions", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat with Orion.

    Features (v6.7.0):
    - Persistent Router + MemoryEngine per connection (not per message)
    - Token-by-token streaming via FastPath.execute_streaming()
    - Council phase updates (Builder -> Reviewer -> Governor)
    - Memory recording + optional user feedback
    - Full logging to ~/.orion/logs/orion.log
    """
    await websocket.accept()

    # Per-connection state
    router_inst = None
    memory_engine = None
    current_workspace = None
    log = _get_orion_log()
    ws_request_count = 0

    if log:
        client_host = websocket.client.host if websocket.client else "unknown"
        log.ws_connect(client=client_host)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            # Handle feedback messages
            if msg_type == "feedback":
                rating = data.get("rating", 0)
                task_desc = data.get("task_description", "")
                if memory_engine and rating and 1 <= rating <= 5:
                    import uuid as _feedback_uuid

                    task_id = str(_feedback_uuid.uuid4())[:8]
                    memory_engine.record_approval(
                        task_id=task_id,
                        task_description=task_desc[:300],
                        rating=rating,
                        feedback=f"User rated {rating}/5 via web",
                        quality_score=rating / 5.0,
                    )
                    if log:
                        log.approval(
                            task_id=task_id, rating=rating, promoted=(rating >= 4 or rating <= 2)
                        )
                    await websocket.send_json(
                        {
                            "type": "feedback_ack",
                            "rating": rating,
                            "pattern": "positive"
                            if rating >= 4
                            else ("anti" if rating <= 2 else "neutral"),
                        }
                    )
                continue

            # Chat message
            ws_request_count += 1
            user_input = data.get("message", "")
            workspace = data.get("workspace", "")
            mode = data.get("mode", "safe")

            if not user_input:
                await websocket.send_json({"type": "error", "message": "No message provided"})
                continue
            if not workspace:
                await websocket.send_json({"type": "error", "message": "No workspace specified"})
                continue

            # Initialize or re-initialize Router + Memory if workspace changed
            if router_inst is None or workspace != current_workspace:
                current_workspace = workspace
                try:
                    from orion.core.memory.engine import get_memory_engine

                    if memory_engine:
                        memory_engine.end_session()
                    memory_engine = get_memory_engine(workspace)
                    memory_engine.start_session()
                except Exception:
                    memory_engine = None

                try:
                    from orion.core.agents.router import RequestRouter

                    router_inst = RequestRouter(
                        workspace,
                        stream_output=False,  # We handle streaming ourselves
                        sandbox_enabled=False,
                        memory_engine=memory_engine,
                    )
                except Exception as e:
                    await websocket.send_json(
                        {"type": "error", "message": f"Router init failed: {e}"}
                    )
                    continue

                if log:
                    log.session_start(workspace=workspace, mode=mode)

            try:
                # Scout classification
                report = None
                route_name = "FAST_PATH"
                if router_inst.scout:
                    report = router_inst.scout.analyze(user_input)
                    route_name = report.route.name

                    await websocket.send_json(
                        {
                            "type": "routing",
                            "route": route_name,
                            "reasoning": report.reasoning,
                            "files": report.relevant_files[:5],
                            "complexity": report.complexity_score,
                            "risk": report.risk_level,
                        }
                    )

                # Streaming for FastPath
                if route_name == "FAST_PATH" and router_inst.fast_path:
                    # Inject memory context
                    memory_ctx = router_inst._get_memory_context(user_input)
                    if memory_ctx:
                        router_inst.fast_path._memory_context = memory_ctx

                    await websocket.send_json({"type": "status", "message": "Thinking..."})

                    collected = []
                    try:
                        async for token in router_inst.fast_path.execute_streaming(
                            user_input, report
                        ):
                            collected.append(token)
                            await websocket.send_json({"type": "token", "content": token})
                        full_response = "".join(collected)
                    except Exception:
                        # Fallback to non-streaming
                        result = await router_inst.fast_path.execute(user_input, report)
                        full_response = result.response
                        await websocket.send_json({"type": "token", "content": full_response})

                    await websocket.send_json(
                        {
                            "type": "complete",
                            "success": True,
                            "response": full_response,
                            "route": route_name,
                        }
                    )

                # Council path (Builder -> Reviewer -> Governor)
                elif route_name == "COUNCIL" and router_inst.council:
                    await websocket.send_json(
                        {"type": "status", "message": "Council deliberating..."}
                    )
                    await websocket.send_json(
                        {
                            "type": "council_phase",
                            "phase": "builder",
                            "message": "Builder generating proposal...",
                        }
                    )

                    result = await router_inst.handle_request(user_input)
                    full_response = result.get("response", "")

                    await websocket.send_json(
                        {
                            "type": "council_phase",
                            "phase": "complete",
                            "message": "Council complete",
                        }
                    )
                    await websocket.send_json(
                        {
                            "type": "complete",
                            "success": result.get("success", False),
                            "response": full_response,
                            "route": route_name,
                            "actions": result.get("actions", []),
                            "execution_time_ms": result.get("execution_time_ms", 0),
                        }
                    )

                # Escalation
                elif route_name == "ESCALATION":
                    await websocket.send_json(
                        {
                            "type": "escalation",
                            "message": "This request was flagged for escalation.",
                            "reason": report.reasoning if report else "Unknown",
                        }
                    )
                    full_response = "Request escalated -- requires human approval."

                # Fallback
                else:
                    result = await router_inst.handle_request(user_input)
                    full_response = result.get("response", "")
                    await websocket.send_json(
                        {
                            "type": "complete",
                            "success": result.get("success", False),
                            "response": full_response,
                            "route": route_name,
                        }
                    )

                # Record interaction in memory
                if router_inst:
                    router_inst.record_interaction(user_input, full_response, route_name)

                if log:
                    log.route(
                        route_name,
                        user_input,
                        complexity=report.complexity_score if report else 0,
                        risk=report.risk_level if report else "",
                    )

            except Exception as e:
                if log:
                    log.error("WebSocket", f"Request failed: {e}", request=user_input[:100])
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        # Clean up session
        if memory_engine:
            with contextlib.suppress(Exception):
                memory_engine.end_session()
        if log:
            client_host = websocket.client.host if websocket.client else "unknown"
            log.ws_disconnect(client=client_host, requests=ws_request_count)
            log.session_end()
    except Exception as e:
        if log:
            log.error("WebSocket", f"Unhandled error: {e}")
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": f"WebSocket error: {e}"})

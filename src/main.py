from __future__ import annotations

import os
import time
from pathlib import Path

from loguru import logger

from src.agents.chat_agent import ChatAgent
from src.agents.proactive_chat import ProactiveChatManager
from src.agents.supervisor import SupervisorAgent
from src.backend.macos.backend import MacOSBackend
from src.core.config import ConfigManager
from src.core.context import ContextManager
from src.core.scheduler import AgentScheduler
from src.core.security import SecurityManager
from src.core.style import StyleManager


class WeChatAgentApp:
    def __init__(
        self,
        backend: MacOSBackend,
        chat_agent: ChatAgent,
        supervisor: SupervisorAgent,
        scheduler: AgentScheduler,
        context: ContextManager,
        proactive: ProactiveChatManager,
    ) -> None:
        self.backend = backend
        self.chat_agent = chat_agent
        self.supervisor = supervisor
        self.scheduler = scheduler
        self.context = context
        self.proactive = proactive

    def start(self) -> None:
        logger.info("Starting WeChatAgent...")
        self.backend.start()
        self.scheduler.start()
        self.proactive.start()
        logger.info("WeChatAgent is running. Press Ctrl+C to stop.")

    def stop(self) -> None:
        logger.info("Stopping WeChatAgent...")
        self.proactive.stop()
        self.scheduler.stop()
        self.backend.stop()
        self.context.close()
        logger.info("WeChatAgent stopped.")


def create_app(
    config_path: str = "config.yaml",
    style_dir: str = "styles",
    db_path: str = "data/agent.db",
) -> WeChatAgentApp:
    config = ConfigManager(Path(config_path))

    context = ContextManager(Path(db_path))
    security = SecurityManager(
        sensitive_words=config.get("security.sensitive_words", []),
        rate_limit=config.get("security.rate_limit", 30),
        pause_keyword=config.get("security.pause_keyword", "#人工"),
    )
    style_manager = StyleManager(Path(style_dir))
    backend = MacOSBackend(
        app_name=config.get("wechat.macos.notification_app", "微信"),
    )
    scheduler = AgentScheduler()

    chat_agent = ChatAgent(
        backend=backend,
        context=context,
        config=config,
        security=security,
        style_manager=style_manager,
    )
    supervisor = SupervisorAgent(
        context=context,
        config=config,
        style_manager=style_manager,
    )

    scheduler.add_supervisor_task(
        interval_cron=config.get("scheduler.supervisor_interval", "0 */6 * * *"),
        callback=supervisor.run_analysis,
    )

    for task in config.get("scheduler.proactive_tasks", []):
        scheduler.add_proactive_task(
            task_id=f"proactive_{task['contact']}",
            contact=task["contact"],
            cron=task["cron"],
            topic_hint=task.get("topic_hint", ""),
            callback=chat_agent.handle_proactive_chat,
        )

    proactive = ProactiveChatManager(
        backend=backend,
        context=context,
        style_manager=style_manager,
    )

    return WeChatAgentApp(
        backend=backend,
        chat_agent=chat_agent,
        supervisor=supervisor,
        scheduler=scheduler,
        context=context,
        proactive=proactive,
    )


def main() -> None:
    logger.add("logs/agent.log", rotation="10 MB", retention="7 days")

    app = create_app()

    # Write PID file for control console to detect
    pid_path = Path("data/runtime.pid")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))

    app.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        pid_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

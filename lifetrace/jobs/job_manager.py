# ruff: noqa: PLC0415
"""
后台任务管理器
负责管理所有后台任务的启动、停止和配置更新
"""

from functools import lru_cache

from lifetrace.core.module_registry import get_module_states
from lifetrace.jobs.scheduler import SchedulerManager, get_scheduler_manager
from lifetrace.util.logging_config import get_logger
from lifetrace.util.settings import settings

logger = get_logger()


def _execute_capture_task():
    from lifetrace.jobs.recorder import execute_capture_task

    return execute_capture_task()


def _execute_todo_capture_task():
    from lifetrace.jobs.todo_recorder import execute_todo_capture_task

    return execute_todo_capture_task()


def _execute_ocr_task():
    from lifetrace.jobs.ocr import execute_ocr_task

    return execute_ocr_task()


def _execute_activity_aggregation_task():
    from lifetrace.jobs.activity_aggregator import execute_activity_aggregation_task

    return execute_activity_aggregation_task()


def _execute_clean_data_task():
    from lifetrace.jobs.clean_data import execute_clean_data_task

    return execute_clean_data_task()


def _execute_deadline_reminder_task():
    from lifetrace.jobs.deadline_reminder import execute_deadline_reminder_task

    return execute_deadline_reminder_task()


def _execute_proactive_ocr_task():
    from lifetrace.jobs.proactive_ocr import execute_proactive_ocr_task

    return execute_proactive_ocr_task()


def execute_audio_recording_status_check():
    """音频录制状态检查任务（用于监控录音状态）

    注意：音频录制实际上由前端WebSocket控制，此任务仅用于状态监控和日志记录
    """
    try:
        # 检查配置
        enabled = settings.get("jobs.audio_recording.enabled", False)
        audio_is_24x7 = settings.get("audio.is_24x7", False)

        # 如果配置开启，记录状态（实际启动由前端控制）
        if enabled and audio_is_24x7:
            logger.debug("音频录制服务已启用（由前端WebSocket控制）")
        else:
            logger.debug("音频录制服务未启用")
    except Exception as e:
        logger.error(f"音频录制状态检查失败: {e}", exc_info=True)


class JobManager:
    """后台任务管理器"""

    def __init__(self):
        """初始化任务管理器"""
        # 后台服务实例
        self.scheduler_manager: SchedulerManager | None = None
        self.module_states = {}

        logger.info("任务管理器已初始化")

    def _get_scheduler(self) -> SchedulerManager | None:
        if not self.scheduler_manager:
            logger.warning("调度器未初始化，跳过任务配置")
            return None
        return self.scheduler_manager

    def _is_module_active(self, *module_ids: str) -> bool:
        """检查模块是否启用且依赖可用"""
        if not self.module_states:
            self.module_states = get_module_states()

        for module_id in module_ids:
            state = self.module_states.get(module_id)
            if not state or not state.enabled or not state.available:
                return False
        return True

    def start_all(self):
        """启动所有后台任务"""
        logger.info("开始启动所有后台任务")

        self.module_states = get_module_states()

        if not self._is_module_active("scheduler"):
            logger.warning("调度器模块未启用或依赖缺失，跳过后台任务启动")
            return

        # 启动调度器
        self._start_scheduler()
        if not self.scheduler_manager:
            logger.warning("调度器启动失败，停止后台任务初始化")
            return

        # 启动录制器任务（事件处理已集成到录制器中，截图后立即处理）
        self._start_recorder_job()

        # 启动 Todo 专用录制器任务（与自动待办检测联动）
        self._start_todo_recorder_job()

        # 启动OCR任务
        self._start_ocr_job()

        # 启动活动聚合任务
        self._start_activity_aggregator()

        # 启动数据清理任务
        self._start_clean_data_job()

        # 启动 DDL 提醒任务
        self._start_deadline_reminder_job()

        # 启动用户自定义自动化任务
        self._start_automation_tasks()

        # 启动主动OCR任务
        self._start_proactive_ocr_job()

        # 启动音频录制状态检查任务
        self._start_audio_recording_job()

        logger.info("所有后台任务已启动")

    def stop_all(self):
        """停止所有后台任务"""
        logger.error("正在停止所有后台任务")

        # 停止调度器（会自动停止所有调度任务）
        self._stop_scheduler()

        logger.error("所有后台任务已停止")

    def _start_scheduler(self):
        """启动调度器"""
        try:
            self.scheduler_manager = get_scheduler_manager()
            self.scheduler_manager.start()
            logger.info("调度器已启动")
        except Exception as e:
            logger.error(f"启动调度器失败: {e}", exc_info=True)

    def _stop_scheduler(self):
        """停止调度器"""
        if self.scheduler_manager:
            try:
                logger.error("正在停止调度器...")
                self.scheduler_manager.shutdown(wait=True)
                logger.error("调度器已停止")
            except Exception as e:
                logger.error(f"停止调度器失败: {e}")

    def _start_recorder_job(self):
        """启动录制器任务"""
        if not self._is_module_active("screenshot"):
            logger.info("截图模块未启用，跳过录制器任务")
            return
        enabled = settings.get("jobs.recorder.enabled")

        try:
            # 仅在启用时预先初始化，避免阻塞启动
            if enabled:
                from lifetrace.jobs.recorder import get_recorder_instance

                get_recorder_instance()
                logger.info("录制器实例已初始化")

            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加录制器定时任务（使用可序列化的函数，无论是否启用都添加）
            recorder_interval = settings.get("jobs.recorder.interval")
            recorder_id = settings.get("jobs.recorder.id")
            scheduler.add_interval_job(
                func=_execute_capture_task,  # 使用模块级别的函数
                job_id="recorder_job",
                name=recorder_id,
                seconds=recorder_interval,
                replace_existing=True,
            )
            logger.info(f"录制器定时任务已添加，间隔: {recorder_interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("recorder_job")
                logger.info("录制器服务未启用，已暂停")
        except Exception as e:
            logger.error(f"启动录制器任务失败: {e}", exc_info=True)

    def _start_todo_recorder_job(self):
        """启动 Todo 专用录制器任务

        此任务与自动待办检测功能联动：
        - 仅在白名单应用激活时截图
        - 截图后直接触发自动待办检测
        - 与通用录制器完全独立
        """
        if not self._is_module_active("todo_extraction", "todo"):
            logger.info("待办提取模块未启用，跳过 Todo 录制器任务")
            return
        enabled = settings.get("jobs.todo_recorder.enabled", False)

        try:
            # 仅在启用时预先初始化
            if enabled:
                from lifetrace.jobs.todo_recorder import get_todo_recorder_instance

                get_todo_recorder_instance()
                logger.info("Todo 录制器实例已初始化")

            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加 Todo 录制器定时任务（无论是否启用都添加）
            todo_recorder_interval = settings.get("jobs.todo_recorder.interval", 5)
            todo_recorder_id = settings.get("jobs.todo_recorder.id", "todo_recorder")
            scheduler.add_interval_job(
                func=_execute_todo_capture_task,
                job_id="todo_recorder_job",
                name=todo_recorder_id,
                seconds=todo_recorder_interval,
                replace_existing=True,
            )
            logger.info(f"Todo 录制器定时任务已添加，间隔: {todo_recorder_interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("todo_recorder_job")
                logger.info("Todo 录制器服务未启用，已暂停")
        except Exception as e:
            logger.error(f"启动 Todo 录制器任务失败: {e}", exc_info=True)

    def _start_ocr_job(self):
        """启动OCR任务"""
        if not self._is_module_active("ocr"):
            logger.info("OCR 模块未启用，跳过 OCR 任务")
            return
        enabled = settings.get("jobs.ocr.enabled")

        try:
            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加OCR定时任务（无论是否启用都添加）
            ocr_interval = settings.get("jobs.ocr.interval")
            ocr_id = settings.get("jobs.ocr.id")
            scheduler.add_interval_job(
                func=_execute_ocr_task,
                job_id="ocr_job",
                name=ocr_id,
                seconds=ocr_interval,
                replace_existing=True,
            )
            logger.info(f"OCR定时任务已添加，间隔: {ocr_interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("ocr_job")
                logger.info("OCR服务未启用，已暂停")
        except Exception as e:
            logger.error(f"启动OCR任务失败: {e}", exc_info=True)

    def _start_activity_aggregator(self):
        """启动活动聚合任务"""
        if not self._is_module_active("activity"):
            logger.info("活动模块未启用，跳过活动聚合任务")
            return
        enabled = settings.get("jobs.activity_aggregator.enabled")

        try:
            # 仅在启用时预先初始化
            if enabled:
                from lifetrace.jobs.activity_aggregator import get_aggregator_instance

                get_aggregator_instance()
                logger.info("活动聚合服务实例已初始化")

            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加到调度器（无论是否启用都添加）
            interval = settings.get("jobs.activity_aggregator.interval")
            aggregator_id = settings.get("jobs.activity_aggregator.id")
            scheduler.add_interval_job(
                func=_execute_activity_aggregation_task,
                job_id="activity_aggregator_job",
                name=aggregator_id,
                seconds=interval,
                replace_existing=True,
            )
            logger.info(f"活动聚合定时任务已添加，间隔: {interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("activity_aggregator_job")
                logger.info("活动聚合服务未启用，已暂停")
        except Exception as e:
            logger.error(f"启动活动聚合服务失败: {e}", exc_info=True)

    def _start_clean_data_job(self):
        """启动数据清理任务"""
        enabled = settings.get("jobs.clean_data.enabled")

        try:
            # 仅在启用时预先初始化
            if enabled:
                from lifetrace.jobs.clean_data import get_clean_data_instance

                get_clean_data_instance()
                logger.info("数据清理服务实例已初始化")

            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加到调度器（无论是否启用都添加）
            interval = settings.get("jobs.clean_data.interval")
            clean_data_id = settings.get("jobs.clean_data.id")
            scheduler.add_interval_job(
                func=_execute_clean_data_task,
                job_id="clean_data_job",
                name=clean_data_id,
                seconds=interval,
                replace_existing=True,
            )
            logger.info(f"数据清理定时任务已添加，间隔: {interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("clean_data_job")
                logger.info("数据清理服务未启用，已暂停")
        except Exception as e:
            logger.error(f"启动数据清理服务失败: {e}", exc_info=True)

    def _start_deadline_reminder_job(self):
        """启动 DDL 提醒任务"""
        if not self._is_module_active("todo", "notification"):
            logger.info("待办/通知模块未启用，跳过 DDL 提醒任务")
            return
        enabled = settings.get("jobs.deadline_reminder.enabled")

        try:
            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 清理旧的定时扫描任务（历史遗留）
            if scheduler.get_job("deadline_reminder_job"):
                scheduler.remove_job("deadline_reminder_job")
                logger.info("已移除旧的 DDL 提醒扫描任务")

            if not enabled:
                from lifetrace.jobs.deadline_reminder import clear_all_todo_reminder_jobs

                clear_all_todo_reminder_jobs()
                logger.info("DDL 提醒服务未启用，已清理提醒任务")
                return

            from lifetrace.jobs.deadline_reminder import sync_all_todo_reminders

            sync_all_todo_reminders()
            logger.info("DDL 提醒任务已同步")
        except Exception as e:
            logger.error(f"启动 DDL 提醒任务失败: {e}", exc_info=True)

    def _start_proactive_ocr_job(self):
        """启动主动OCR任务"""
        if not self._is_module_active("proactive_ocr"):
            logger.info("主动 OCR 模块未启用，跳过主动 OCR 任务")
            return
        enabled = settings.get("jobs.proactive_ocr.enabled", False)

        try:
            # 仅在启用时预先初始化
            if enabled:
                from lifetrace.jobs.proactive_ocr.service import get_proactive_ocr_service

                get_proactive_ocr_service()
                logger.info("主动OCR服务实例已初始化")

            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加到调度器（无论是否启用都添加）
            interval = settings.get("jobs.proactive_ocr.interval", 1.0)
            proactive_ocr_id = settings.get("jobs.proactive_ocr.id", "proactive_ocr")
            scheduler.add_interval_job(
                func=_execute_proactive_ocr_task,
                job_id="proactive_ocr_job",
                name=proactive_ocr_id,
                seconds=interval,
                replace_existing=True,
            )
            logger.info(f"主动OCR定时任务已添加，间隔: {interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("proactive_ocr_job")
                logger.info("主动OCR服务未启用，已暂停")
            else:
                # 如果启用，立即执行一次以启动服务
                _execute_proactive_ocr_task()
        except Exception as e:
            logger.error(f"启动主动OCR任务失败: {e}", exc_info=True)

    def _start_automation_tasks(self):
        """启动用户自定义自动化任务"""
        if not self._is_module_active("automation", "scheduler"):
            logger.info("自动化模块未启用，跳过自动化任务")
            return

        scheduler = self._get_scheduler()
        if not scheduler:
            return

        try:
            from lifetrace.services.automation_task_service import AutomationTaskService

            AutomationTaskService().sync_all_tasks()
            logger.info("自动化任务同步完成")
        except Exception as e:
            logger.error(f"自动化任务同步失败: {e}", exc_info=True)

    def _start_audio_recording_job(self):
        """启动音频录制状态检查任务

        注意：音频录制实际上由前端WebSocket控制，此任务仅用于状态监控
        """
        if not self._is_module_active("audio"):
            logger.info("音频模块未启用，跳过音频录制状态检查任务")
            return
        enabled = settings.get("jobs.audio_recording.enabled", False)

        try:
            scheduler = self._get_scheduler()
            if not scheduler:
                return

            # 添加到调度器（无论是否启用都添加）
            interval = settings.get("jobs.audio_recording.interval", 60)
            audio_recording_id = settings.get("jobs.audio_recording.id", "audio_recording")
            scheduler.add_interval_job(
                func=execute_audio_recording_status_check,
                job_id="audio_recording_job",
                name=audio_recording_id,
                seconds=interval,
                replace_existing=True,
            )
            logger.info(f"音频录制状态检查任务已添加，间隔: {interval}秒")

            # 如果未启用，则暂停任务
            if not enabled:
                scheduler.pause_job("audio_recording_job")
                logger.info("音频录制服务未启用，已暂停")
            else:
                logger.info("音频录制服务已启用（由前端WebSocket控制）")
        except Exception as e:
            logger.error(f"启动音频录制任务失败: {e}", exc_info=True)


# 全局单例


@lru_cache(maxsize=1)
def get_job_manager() -> JobManager:
    """获取任务管理器单例"""
    return JobManager()

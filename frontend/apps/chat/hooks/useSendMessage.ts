import type { QueryClient } from "@tanstack/react-query";
import type { useTranslations } from "next-intl";
import { useCallback } from "react";
import { flushSync } from "react-dom";
import type { SessionCacheReturn } from "@/apps/chat/hooks/useSessionCache";
import type { StreamControllerReturn } from "@/apps/chat/hooks/useStreamController";
import type { ToolCallTrackerReturn } from "@/apps/chat/hooks/useToolCallTracker";
import type { ChatMessage } from "@/apps/chat/types";
import { createId } from "@/apps/chat/utils/id";
import {
	buildPayloadMessage,
	getModeForBackend,
} from "@/apps/chat/utils/messageBuilder";
import {
	handleEmptyResponse,
	handleStreamError,
} from "@/apps/chat/utils/responseHandlers";
import {
	buildHierarchicalTodoContext,
	buildTodoContextBlock,
} from "@/apps/chat/utils/todoContext";
import type { ToolCallEvent } from "@/lib/api";
import { sendChatMessageStream } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useChatStore } from "@/lib/store/chat-store";
import type { Todo } from "@/lib/types";

/**
 * useSendMessage 参数
 */
export interface UseSendMessageParams {
	/** 语言设置 */
	locale: string;
	/** 是否有选中的待办 */
	hasSelection: boolean;
	/** 选中的待办列表 */
	effectiveTodos: Todo[];
	/** 所有待办列表 */
	todos: Todo[];
	/** 选中的 Agno 工具 */
	selectedAgnoTools: string[];
	/** 选中的外部工具 */
	selectedExternalTools: string[];
	/** 会话缓存 hook */
	sessionCache: SessionCacheReturn;
	/** 流式控制器 hook */
	streamController: StreamControllerReturn;
	/** 工具调用跟踪器 hook */
	toolCallTracker: ToolCallTrackerReturn;
	/** Query Client */
	queryClient: QueryClient;
	/** 翻译函数 */
	t: ReturnType<typeof useTranslations<"chat">>;
	tCommon: ReturnType<typeof useTranslations<"common">>;
	/** 设置 conversationId */
	setConversationId: (id: string | null) => void;
	/** 设置消息列表 */
	setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
	/** 设置输入框内容 */
	setInputValue: React.Dispatch<React.SetStateAction<string>>;
	/** 设置流式状态 */
	setIsStreaming: React.Dispatch<React.SetStateAction<boolean>>;
	/** 设置错误状态 */
	setError: React.Dispatch<React.SetStateAction<string | null>>;
}

/**
 * useSendMessage 返回值
 */
export interface SendMessageReturn {
	/** 发送消息 */
	sendMessage: (text: string, clearInput?: boolean) => Promise<void>;
}

/**
 * 处理发送消息的核心逻辑
 */
export const useSendMessage = ({
	locale,
	hasSelection,
	effectiveTodos,
	todos,
	selectedAgnoTools,
	selectedExternalTools,
	sessionCache,
	streamController,
	toolCallTracker,
	queryClient,
	t,
	tCommon,
	setConversationId,
	setMessages,
	setInputValue,
	setIsStreaming,
	setError,
}: UseSendMessageParams): SendMessageReturn => {
	/**
	 * 发送消息
	 * @param text - 要发送的文本
	 * @param clearInput - 是否清空输入框
	 */
	const sendMessage = useCallback(
		async (text: string, clearInput = false) => {
			const trimmedText = text.trim();
			if (!trimmedText) return;

			// 创建请求
			const { requestId, abortController } = streamController.createRequest();
			const currentConversationId = useChatStore.getState().conversationId;

			if (clearInput) {
				setInputValue("");
			}
			setError(null);

			// 重置工具调用跟踪器
			toolCallTracker.reset();

			// 构建待办上下文
			const todoContext = hasSelection
				? buildHierarchicalTodoContext(effectiveTodos, todos, t, tCommon)
				: buildTodoContextBlock([], t("noTodoContext"), t);
			const userLabel = t("userInput");

			// 使用工具函数构建 payload
			const { payloadMessage, systemPromptForBackend, contextForBackend } =
				buildPayloadMessage({
					trimmedText,
					userLabel,
					todoContext,
				});

			// 创建消息
			const userMessage: ChatMessage = {
				id: createId(),
				role: "user",
				content: trimmedText,
			};
			const assistantMessageId = createId();
			const initialMessages: ChatMessage[] = [
				userMessage,
				{ id: assistantMessageId, role: "assistant", content: "" },
			];

			setMessages((prev) => [...prev, ...initialMessages]);
			setIsStreaming(true);

			let assistantContent = "";
			let requestSessionId = currentConversationId;

			// 本地缓存当前消息的 toolCallSteps，避免竞态条件
			let cachedToolCallSteps: ReturnType<
				typeof toolCallTracker.getToolCallSteps
			> = [];

			// 辅助函数：更新消息
			const updateAssistantMessage = (
				content: string,
				newToolCallSteps?: ReturnType<typeof toolCallTracker.getToolCallSteps>,
			) => {
				// 如果传入了非空的新步骤，更新本地缓存
				if (newToolCallSteps && newToolCallSteps.length > 0) {
					cachedToolCallSteps = newToolCallSteps;
				}

				// 使用本地缓存的步骤，确保不会丢失
				const stepsToUse =
					cachedToolCallSteps.length > 0 ? cachedToolCallSteps : undefined;

				const messageUpdater = (prev: ChatMessage[]) =>
					prev.map((msg) =>
						msg.id === assistantMessageId
							? { ...msg, content, toolCallSteps: stepsToUse }
							: msg,
					);

				// 总是更新缓存
				if (requestSessionId) {
					sessionCache.updateMessages(requestSessionId, messageUpdater);
				}

				// 检查是否应该更新 UI
				const currentDisplayedSessionId =
					useChatStore.getState().conversationId;
				if (
					requestSessionId &&
					currentDisplayedSessionId === requestSessionId
				) {
					flushSync(() => {
						setMessages(messageUpdater);
					});
				}
			};

			try {
				const modeForBackend = getModeForBackend();

				await sendChatMessageStream(
					{
						message: payloadMessage,
						userInput: trimmedText,
						context: contextForBackend,
						systemPrompt: systemPromptForBackend,
						conversationId: currentConversationId || undefined,
						useRag: false,
						mode: modeForBackend,
						selectedTools: selectedAgnoTools,
						externalTools: selectedExternalTools,
					},
					// onChunk 回调
					(chunk) => {
						if (abortController.signal.aborted) return;

						assistantContent += chunk;
						updateAssistantMessage(
							assistantContent,
							toolCallTracker.getToolCallSteps(),
						);
					},
					// onSessionId 回调
					(sessionId) => {
						const effectiveSessionId = currentConversationId || sessionId;
						requestSessionId = effectiveSessionId;

						sessionCache.markStreaming(effectiveSessionId);

						// 初始化缓存
						if (!sessionCache.getMessages(effectiveSessionId)) {
							const currentMsgs = [
								userMessage,
								{
									id: assistantMessageId,
									role: "assistant" as const,
									content: assistantContent,
								},
							];
							sessionCache.saveMessages(effectiveSessionId, currentMsgs);
						}

						// 只有活跃请求才更新 conversationId
						if (streamController.isActiveRequest(requestId)) {
							const isNewSession = !currentConversationId;
							setConversationId(effectiveSessionId);

							if (isNewSession) {
								void queryClient.invalidateQueries({
									queryKey: queryKeys.chatHistory.all,
								});
							}
						}
					},
					abortController.signal,
					locale,
					// onToolEvent 回调
					(event: ToolCallEvent) => {
						if (abortController.signal.aborted) return;

						const updatedSteps = toolCallTracker.handleToolEvent(event);
						if (updatedSteps) {
							updateAssistantMessage(assistantContent, updatedSteps);
						}
					},
				);

				// 流结束后，强制完成所有还在运行中的工具调用步骤（兜底清理）
				const finalizedSteps = toolCallTracker.finalizeRunningSteps();
				if (finalizedSteps) {
					updateAssistantMessage(assistantContent, finalizedSteps);
				}

				// 处理响应完成后的逻辑
				if (!assistantContent) {
					handleEmptyResponse(assistantMessageId, t, setMessages);
				}
			} catch (err) {
				handleStreamError(
					err,
					abortController,
					assistantContent,
					assistantMessageId,
					t,
					setMessages,
					setError,
				);
			} finally {
				// 清理
				if (requestSessionId) {
					sessionCache.unmarkStreaming(requestSessionId);

					// 保存最终消息状态
					const sessionIdToSave = requestSessionId;
					setMessages((currentMsgs) => {
						if (currentMsgs.length > 0) {
							sessionCache.saveMessages(sessionIdToSave, currentMsgs);
						}
						return currentMsgs;
					});
				}

				// 检查是否应该更新 isStreaming
				const currentDisplayedSessionId =
					useChatStore.getState().conversationId;
				if (
					requestSessionId &&
					currentDisplayedSessionId === requestSessionId
				) {
					setIsStreaming(false);
				}

				// 清理 abortController
				if (streamController.isActiveRequest(requestId)) {
					streamController.cleanupAbortController();
				}
			}
		},
		[
			effectiveTodos,
			hasSelection,
			locale,
			queryClient,
			selectedAgnoTools,
			selectedExternalTools,
			sessionCache,
			setConversationId,
			setError,
			setInputValue,
			setIsStreaming,
			setMessages,
			streamController,
			t,
			tCommon,
			todos,
			toolCallTracker,
		],
	);

	return { sendMessage };
};

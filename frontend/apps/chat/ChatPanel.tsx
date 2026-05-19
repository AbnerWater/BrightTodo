"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BreakdownStageRenderer } from "@/apps/chat/components/breakdown/BreakdownStageRenderer";
import { ChatInputSection } from "@/apps/chat/components/input/ChatInputSection";
import { PromptSuggestions } from "@/apps/chat/components/input/PromptSuggestions";
import { HeaderBar } from "@/apps/chat/components/layout/HeaderBar";
import { HistoryDrawer } from "@/apps/chat/components/layout/HistoryDrawer";
import { MessageList } from "@/apps/chat/components/message/MessageList";
import { useBreakdownQuestionnaire } from "@/apps/chat/hooks/useBreakdownQuestionnaire";
import { useChatController } from "@/apps/chat/hooks/useChatController";
import { useChatStore } from "@/lib/store/chat-store";
import { useLocaleStore } from "@/lib/store/locale";
import { useTodoStore } from "@/lib/store/todo-store";

export function ChatPanel() {
	const { locale } = useLocaleStore();
	const tChat = useTranslations("chat");
	const tPage = useTranslations("page");

	// 从 Zustand 获取 UI 状态
	const { selectedTodoIds, clearTodoSelection, toggleTodoSelection } =
		useTodoStore();

	// 获取 pendingPrompt（其他组件触发的待发送消息）
	const { pendingPrompt, pendingNewChat, setPendingPrompt } = useChatStore();

	// 使用 Breakdown Questionnaire hook
	const breakdownQuestionnaire = useBreakdownQuestionnaire();

	// 使用 Chat Controller hook
	const chatController = useChatController({
		locale,
		selectedTodoIds,
	});

	// 处理预设 Prompt 选择：直接发送消息（复用 sendMessage 逻辑）
	const handleSelectPrompt = useCallback(
		(prompt: string) => {
			void chatController.sendMessage(prompt);
		},
		[chatController],
	);

	// 监听 pendingPrompt 变化，自动发送消息（由其他组件触发，如 TodoCard 的"获取建议"按钮）
	useEffect(() => {
		if (pendingPrompt) {
			// 如果需要新开会话，先清空当前会话（keepStreaming=true 让旧的流式输出继续在后台运行）
			if (pendingNewChat) {
				chatController.handleNewChat(true);
			}
			// 使用 setTimeout 确保新会话状态已更新后再发送消息
			setTimeout(() => {
				void chatController.sendMessage(pendingPrompt);
			}, 0);
			// 清空 pendingPrompt，避免重复发送
			setPendingPrompt(null);
		}
	}, [pendingPrompt, pendingNewChat, chatController, setPendingPrompt]);

	const [showTodosExpanded, setShowTodosExpanded] = useState(false);

	const typingText = useMemo(() => tChat("aiThinking"), [tChat]);

	const formatMessageCount = useCallback(
		(count?: number) => tPage("messagesCount", { count: count ?? 0 }),
		[tPage],
	);

	// 判断是否显示首页（用于在输入框上方显示建议按钮）
	const shouldShowSuggestions = useMemo(() => {
		const messages = chatController.messages;
		if (messages.length === 0) return true;
		if (messages.length === 1 && messages[0].role === "assistant") return true;
		if (messages.every((msg) => msg.role === "assistant")) return true;
		return false;
	}, [chatController.messages]);

	return (
		<div className="flex h-full flex-col bg-background">
			<HeaderBar
				chatHistoryLabel={tPage("chatHistory")}
				newChatLabel={tPage("newChat")}
				onToggleHistory={() =>
					chatController.setHistoryOpen(!chatController.historyOpen)
				}
				onNewChat={chatController.handleNewChat}
			/>

			{chatController.historyOpen && (
				<HistoryDrawer
					historyLoading={chatController.historyLoading}
					historyError={chatController.historyError}
					sessions={chatController.sessions}
					conversationId={chatController.conversationId}
					formatMessageCount={formatMessageCount}
					labels={{
						recentSessions: tPage("recentSessions"),
						noHistory: tPage("noHistory"),
						loading: tChat("loading"),
						chatHistory: tPage("chatHistory"),
					}}
					onSelectSession={chatController.handleLoadSession}
				/>
			)}

			<BreakdownStageRenderer
				stage={breakdownQuestionnaire.stage}
				questions={breakdownQuestionnaire.questions}
				answers={breakdownQuestionnaire.answers}
				summary={breakdownQuestionnaire.summary}
				subtasks={breakdownQuestionnaire.subtasks}
				breakdownLoading={breakdownQuestionnaire.breakdownLoading}
				isGeneratingSummary={breakdownQuestionnaire.isGeneratingSummary}
				summaryStreamingText={breakdownQuestionnaire.summaryStreamingText}
				isGeneratingQuestions={breakdownQuestionnaire.isGeneratingQuestions}
				questionStreamingCount={breakdownQuestionnaire.questionStreamingCount}
				questionStreamingTitle={breakdownQuestionnaire.questionStreamingTitle}
				breakdownError={breakdownQuestionnaire.breakdownError}
				locale={locale}
				onAnswerChange={breakdownQuestionnaire.setAnswer}
				onSubmit={breakdownQuestionnaire.handleSubmitAnswers}
				onAccept={breakdownQuestionnaire.handleAcceptBreakdown}
			/>

			{(breakdownQuestionnaire.stage === "idle" ||
				breakdownQuestionnaire.stage === "completed") && (
				<MessageList
					messages={chatController.messages}
					isStreaming={chatController.isStreaming}
					typingText={typingText}
					effectiveTodos={chatController.effectiveTodos}
				/>
			)}

			{/* 首页时在输入框上方显示建议按钮 */}
			{shouldShowSuggestions &&
				(breakdownQuestionnaire.stage === "idle" ||
					breakdownQuestionnaire.stage === "completed") && (
					<PromptSuggestions onSelect={handleSelectPrompt} className="pb-4" />
				)}

			<ChatInputSection
				locale={locale}
				inputValue={chatController.inputValue}
				isStreaming={chatController.isStreaming}
				error={chatController.error}
				effectiveTodos={chatController.effectiveTodos}
				hasSelection={chatController.hasSelection}
				showTodosExpanded={showTodosExpanded}
				onInputChange={chatController.setInputValue}
				onSend={chatController.handleSend}
				onStop={chatController.handleStop}
				onKeyDown={chatController.handleKeyDown}
				onCompositionStart={() => chatController.setIsComposing(true)}
				onCompositionEnd={() => chatController.setIsComposing(false)}
				onToggleExpand={() => setShowTodosExpanded((prev) => !prev)}
				onClearSelection={clearTodoSelection}
				onToggleTodo={toggleTodoSelection}
			/>
		</div>
	);
}

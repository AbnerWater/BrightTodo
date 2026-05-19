/**
 * 消息构建参数
 */
export interface BuildPayloadMessageParams {
	trimmedText: string;
	userLabel: string;
	todoContext: string;
}

/**
 * 消息构建结果
 */
export interface PayloadMessageResult {
	/** 发送给后端的完整消息 */
	payloadMessage: string;
	/** 系统提示词（可选，用于后端保存） */
	systemPromptForBackend?: string;
	/** 上下文（可选，用于后端保存） */
	contextForBackend?: string;
}

/**
 * 构建发送给后端的 payload 消息
 */
export const buildPayloadMessage = (
	params: BuildPayloadMessageParams,
): PayloadMessageResult => {
	const { trimmedText, userLabel, todoContext } = params;

	return {
		payloadMessage: `${todoContext}

${userLabel}: ${trimmedText}`,
		contextForBackend: todoContext,
	};
};

/**
 * 将前端聊天模式映射为后端模式
 */
export const getModeForBackend = (): string => "agno";

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Paperclip } from "lucide-react";
import { useTranslations } from "next-intl";
import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	type AttachmentPlanDraft,
	ChatImportTodosPanel,
	type UploadFileItem,
} from "@/apps/chat/components/input/ChatImportTodosPanel";
import { InputBox } from "@/apps/chat/components/input/InputBox";
import { LinkedTodos } from "@/apps/chat/components/input/LinkedTodos";
import { ToolSelector } from "@/apps/chat/components/input/ToolSelector";
import { queryKeys } from "@/lib/query/keys";
import type { Todo, TodoPriority } from "@/lib/types";
import { cn } from "@/lib/utils";

type ChatInputSectionProps = {
	locale: string;
	conversationId: string | null;
	inputValue: string;
	isStreaming: boolean;
	error: string | null;
	effectiveTodos: Todo[];
	hasSelection: boolean;
	showTodosExpanded: boolean;
	onInputChange: (value: string) => void;
	onSend: () => void;
	onStop?: () => void;
	onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
	onCompositionStart: () => void;
	onCompositionEnd: () => void;
	onToggleExpand: () => void;
	onClearSelection: () => void;
	onToggleTodo: (todoId: number) => void;
};

type AttachmentPlanApiFileResult = {
	file_name: string;
	status: "ready" | "failed";
	message: string | null;
	error_code: string | null;
};

type AttachmentPlanApiTodo = {
	plan_item_id: string;
	title: string;
	description: string | null;
	priority: TodoPriority;
	due: string | null;
	duration: string | null;
	suggested_start: string | null;
	suggested_end: string | null;
	schedule_reason: string | null;
	source_file_indices: number[];
	source_files: string[];
	source_text: string | null;
	confidence: number;
};

type AttachmentPlanApiResponse = {
	plan_id: string;
	file_results: AttachmentPlanApiFileResult[];
	proposed_todos: AttachmentPlanApiTodo[];
	schedule_summary: string;
};

type AttachmentPlanConfirmResponse = {
	created_todos: Array<{ id: number; name: string; status: string }>;
};

const SUPPORTED_IMPORT_ACCEPT =
	".png,.jpg,.jpeg,.webp,.txt,.md,.markdown,.csv,.json,.pdf,.docx";
const MAX_IMPORT_FILES = 5;
const MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024;

const makeClientId = () =>
	typeof crypto !== "undefined" && "randomUUID" in crypto
		? crypto.randomUUID()
		: `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const parseApiError = async (response: Response) => {
	try {
		const data = (await response.json()) as { message?: string; detail?: string };
		return data.message || data.detail || `HTTP ${response.status}`;
	} catch {
		return `HTTP ${response.status}`;
	}
};

const toPlanDraft = (todo: AttachmentPlanApiTodo): AttachmentPlanDraft => ({
	id: makeClientId(),
	planItemId: todo.plan_item_id,
	title: todo.title,
	priority: todo.priority,
	due: todo.due,
	duration: todo.duration,
	description: todo.description,
	suggestedStart: todo.suggested_start,
	suggestedEnd: todo.suggested_end,
	scheduleReason: todo.schedule_reason,
	sourceFileIndices: todo.source_file_indices ?? [],
	sourceFiles: todo.source_files ?? [],
	sourceText: todo.source_text,
	confidence: todo.confidence,
});

const toApiTodo = (item: AttachmentPlanDraft): AttachmentPlanApiTodo => ({
	plan_item_id: item.planItemId,
	title: item.title.trim(),
	description: item.description,
	priority: item.priority,
	due: item.due,
	duration: item.duration,
	suggested_start: item.suggestedStart,
	suggested_end: item.suggestedEnd,
	schedule_reason: item.scheduleReason,
	source_file_indices: item.sourceFileIndices,
	source_files: item.sourceFiles,
	source_text: item.sourceText,
	confidence: item.confidence,
});

export function ChatInputSection({
	locale,
	conversationId,
	inputValue,
	isStreaming,
	error,
	effectiveTodos,
	hasSelection,
	showTodosExpanded,
	onInputChange,
	onSend,
	onStop,
	onKeyDown,
	onCompositionStart,
	onCompositionEnd,
	onToggleExpand,
	onClearSelection,
	onToggleTodo,
}: ChatInputSectionProps) {
	const tPage = useTranslations("page");
	const tImport = useTranslations("chat.importTodos");
	const queryClient = useQueryClient();
	const modeMenuRef = useRef<HTMLDivElement | null>(null);
	const fileInputRef = useRef<HTMLInputElement | null>(null);
	const filesRef = useRef<UploadFileItem[]>([]);
	const planIdRef = useRef<string | null>(null);
	const promptAppliedRef = useRef(false);
	const inputPlaceholder = tPage("chatInputPlaceholder");
	const [files, setFiles] = useState<UploadFileItem[]>([]);
	const [planItems, setPlanItems] = useState<AttachmentPlanDraft[]>([]);
	const [planId, setPlanId] = useState<string | null>(null);
	const [isPlanning, setIsPlanning] = useState(false);
	const [isCreating, setIsCreating] = useState(false);
	const [uploadError, setUploadError] = useState<string | null>(null);
	const [successMessage, setSuccessMessage] = useState<string | null>(null);
	const [scheduleSummary, setScheduleSummary] = useState<string | null>(null);

	useEffect(() => {
		filesRef.current = files;
	}, [files]);

	useEffect(() => {
		planIdRef.current = planId;
	}, [planId]);

	useEffect(() => {
		return () => {
			for (const file of filesRef.current) {
				if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
			}
			const currentPlanId = planIdRef.current;
			if (currentPlanId) {
				void fetch(`/api/agent/attachment-plan/${currentPlanId}`, {
					method: "DELETE",
				}).catch(() => undefined);
			}
		};
	}, []);

	const clearRemotePlan = useCallback((currentPlanId: string | null) => {
		if (!currentPlanId) return;
		void fetch(`/api/agent/attachment-plan/${currentPlanId}`, {
			method: "DELETE",
		}).catch(() => undefined);
	}, []);

	const clearAll = useCallback(() => {
		for (const file of files) {
			if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
		}
		clearRemotePlan(planId);
		setFiles([]);
		setPlanItems([]);
		setPlanId(null);
		setUploadError(null);
		setSuccessMessage(null);
		setScheduleSummary(null);
		promptAppliedRef.current = false;
		if (fileInputRef.current) fileInputRef.current.value = "";
	}, [clearRemotePlan, files, planId]);

	const appendDefaultPrompt = useCallback(
		(selectedFiles: File[]) => {
			if (promptAppliedRef.current) return;
			const prompt = tImport("promptTemplate", {
				files: selectedFiles.map((file) => file.name).join(", "),
			});
			const current = inputValue.trim();
			onInputChange(current ? `${inputValue.trimEnd()}\n\n${prompt}` : prompt);
			promptAppliedRef.current = true;
		},
		[inputValue, onInputChange, tImport],
	);

	const queueFiles = useCallback(
		(selectedFiles: File[]) => {
			if (selectedFiles.length === 0) return;
			if (filesRef.current.length + selectedFiles.length > MAX_IMPORT_FILES) {
				setUploadError(tImport("tooManyFiles"));
				return;
			}
			const oversized = selectedFiles.find(
				(file) => file.size > MAX_IMPORT_FILE_BYTES,
			);
			if (oversized) {
				setUploadError(tImport("sizeLimit"));
				return;
			}

			const uploadItems = selectedFiles.map((file) => ({
				id: makeClientId(),
				name: file.name,
				type: file.type,
				size: file.size,
				status: "ready" as const,
				message: tImport("ready"),
				previewUrl: file.type.startsWith("image/")
					? URL.createObjectURL(file)
					: undefined,
				file,
			}));
			setFiles((current) => [...current, ...uploadItems]);
			setPlanItems([]);
			setPlanId((currentPlanId) => {
				clearRemotePlan(currentPlanId);
				return null;
			});
			setUploadError(null);
			setSuccessMessage(null);
			setScheduleSummary(null);
			appendDefaultPrompt(selectedFiles);
			if (fileInputRef.current) fileInputRef.current.value = "";
		},
		[appendDefaultPrompt, clearRemotePlan, tImport],
	);

	const handleFileChange = useCallback(
		(event: React.ChangeEvent<HTMLInputElement>) => {
			queueFiles(Array.from(event.target.files ?? []));
		},
		[queueFiles],
	);

	const removeFile = useCallback(
		(fileId: string) => {
			const target = files.find((file) => file.id === fileId);
			if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
			setFiles((current) => current.filter((file) => file.id !== fileId));
			if (typeof target?.sourceIndex === "number") {
				setPlanItems((current) =>
					current.filter(
						(item) => !item.sourceFileIndices.includes(target.sourceIndex ?? -1),
					),
				);
			}
		},
		[files],
	);

	const updatePlanItem = useCallback(
		(itemId: string, patch: Partial<AttachmentPlanDraft>) => {
			setPlanItems((current) =>
				current.map((item) =>
					item.id === itemId ? { ...item, ...patch } : item,
				),
			);
		},
		[],
	);

	const submitAttachmentPlan = useCallback(async () => {
		const currentFiles = filesRef.current;
		if (currentFiles.length === 0) {
			onSend();
			return;
		}
		const prompt = inputValue.trim();
		if (!prompt) {
			setUploadError(tImport("emptyPrompt"));
			return;
		}

		setIsPlanning(true);
		setUploadError(null);
		setSuccessMessage(null);
		setScheduleSummary(null);
		setPlanItems([]);
		clearRemotePlan(planId);
		setPlanId(null);
		setFiles((current) =>
			current.map((file, index) => ({
				...file,
				status: "planning",
				message: tImport("planning"),
				sourceIndex: index,
			})),
		);

		const formData = new FormData();
		for (const file of currentFiles) {
			formData.append("files", file.file);
		}
		formData.append("prompt", prompt);
		formData.append("reference_time", new Date().toISOString());
		formData.append("planning_start", new Date().toISOString());
		if (conversationId) {
			formData.append("conversation_id", conversationId);
		}

		try {
			const response = await fetch("/api/agent/attachment-plan", {
				method: "POST",
				body: formData,
			});
			if (!response.ok) {
				throw new Error(await parseApiError(response));
			}
			const data = (await response.json()) as AttachmentPlanApiResponse;
			const plannedItems = data.proposed_todos.map(toPlanDraft);
			setPlanId(data.plan_id);
			setPlanItems(plannedItems);
			setScheduleSummary(data.schedule_summary || null);
			setFiles((current) =>
				current.map((item, index) => {
					const result = data.file_results[index];
					return {
						...item,
						sourceIndex: index,
						status: result?.status === "failed" ? "failed" : "planned",
						message:
							result?.message ||
							(result?.error_code ? result.error_code : tImport("planned")),
					};
				}),
			);
			if (plannedItems.length === 0) {
				setUploadError(tImport("noPlanTodos"));
			} else {
				setSuccessMessage(tImport("planSuccess", { count: plannedItems.length }));
				onInputChange("");
			}
		} catch (planErr) {
			const message = planErr instanceof Error ? planErr.message : String(planErr);
			setUploadError(tImport("planFailed", { error: message }));
			setFiles((current) =>
				current.map((item) => ({
					...item,
					status: "failed",
					message: tImport("failed"),
				})),
			);
		} finally {
			setIsPlanning(false);
		}
	}, [
		clearRemotePlan,
		conversationId,
		inputValue,
		onInputChange,
		onSend,
		planId,
		tImport,
	]);

	const confirmCreate = useCallback(async () => {
		const validItems = planItems.filter((item) => item.title.trim());
		if (!planId || validItems.length === 0) {
			setUploadError(tImport("emptyTaskTitle"));
			return;
		}

		setIsCreating(true);
		setUploadError(null);
		try {
			const response = await fetch(
				`/api/agent/attachment-plan/${planId}/confirm`,
				{
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						proposed_todos: validItems.map(toApiTodo),
					}),
				},
			);
			if (!response.ok) {
				throw new Error(await parseApiError(response));
			}
			const data = (await response.json()) as AttachmentPlanConfirmResponse;
			for (const file of files) {
				if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
			}
			setFiles([]);
			setPlanItems([]);
			setPlanId(null);
			setScheduleSummary(null);
			setUploadError(null);
			setSuccessMessage(
				tImport("createSuccess", { count: data.created_todos.length }),
			);
			promptAppliedRef.current = false;
			if (fileInputRef.current) fileInputRef.current.value = "";
			void queryClient.invalidateQueries({ queryKey: queryKeys.todos.all });
		} catch (createErr) {
			const message =
				createErr instanceof Error ? createErr.message : String(createErr);
			setUploadError(tImport("createFailed", { error: message }));
		} finally {
			setIsCreating(false);
		}
	}, [files, planId, planItems, queryClient, tImport]);

	const handleSend = useCallback(() => {
		if (filesRef.current.length > 0) {
			void submitAttachmentPlan();
			return;
		}
		onSend();
	}, [onSend, submitAttachmentPlan]);

	const handleKeyDown = useCallback(
		(event: React.KeyboardEvent<HTMLTextAreaElement>) => {
			if (
				filesRef.current.length > 0 &&
				event.key === "Enter" &&
				!event.shiftKey &&
				!event.nativeEvent.isComposing
			) {
				event.preventDefault();
				void submitAttachmentPlan();
				return;
			}
			onKeyDown(event);
		},
		[onKeyDown, submitAttachmentPlan],
	);

	return (
		<div className="bg-background p-4">
			<input
				ref={fileInputRef}
				type="file"
				multiple
				accept={SUPPORTED_IMPORT_ACCEPT}
				className="hidden"
				onChange={handleFileChange}
			/>
			<ChatImportTodosPanel
				files={files}
				planItems={planItems}
				isPlanning={isPlanning}
				isCreating={isCreating}
				successMessage={successMessage}
				errorMessage={uploadError}
				scheduleSummary={scheduleSummary}
				onRemoveFile={removeFile}
				onRemovePlanItem={(itemId) =>
					setPlanItems((current) => current.filter((item) => item.id !== itemId))
				}
				onUpdatePlanItem={updatePlanItem}
				onConfirmCreate={confirmCreate}
				onClearAll={clearAll}
			/>
			<InputBox
				linkedTodos={
					<LinkedTodos
						effectiveTodos={effectiveTodos}
						hasSelection={hasSelection}
						locale={locale}
						showTodosExpanded={showTodosExpanded}
						onToggleExpand={onToggleExpand}
						onClearSelection={onClearSelection}
						onToggleTodo={onToggleTodo}
					/>
				}
				modeSwitcher={
					<div className="flex items-center gap-2" ref={modeMenuRef}>
						<ToolSelector disabled={isStreaming || isPlanning} />
					</div>
				}
				inputValue={inputValue}
				placeholder={inputPlaceholder}
				isStreaming={isStreaming || isPlanning}
				locale={locale}
				uploadButton={
					<button
						type="button"
						onClick={() => fileInputRef.current?.click()}
						disabled={isStreaming || isPlanning || isCreating}
						className={cn(
							"flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground",
							"hover:bg-foreground/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
							"disabled:cursor-not-allowed disabled:opacity-50",
						)}
						aria-label={tImport("uploadLabel")}
						title={tImport("uploadLabel")}
					>
						<Paperclip className="h-4 w-4" />
					</button>
				}
				onChange={onInputChange}
				onSend={handleSend}
				onStop={onStop}
				onKeyDown={handleKeyDown}
				onCompositionStart={onCompositionStart}
				onCompositionEnd={onCompositionEnd}
			/>

			{error && <p className="mt-2 text-sm">{error}</p>}
		</div>
	);
}

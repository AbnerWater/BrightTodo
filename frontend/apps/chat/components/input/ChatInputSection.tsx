"use client";

import { Paperclip } from "lucide-react";
import { useTranslations } from "next-intl";
import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	ChatImportTodosPanel,
	type ImportTodoDraft,
	type UploadFileItem,
} from "@/apps/chat/components/input/ChatImportTodosPanel";
import { InputBox } from "@/apps/chat/components/input/InputBox";
import { LinkedTodos } from "@/apps/chat/components/input/LinkedTodos";
import { ToolSelector } from "@/apps/chat/components/input/ToolSelector";
import { useTodoMutations } from "@/lib/query";
import type { Todo } from "@/lib/types";
import { cn } from "@/lib/utils";

type ChatInputSectionProps = {
	locale: string;
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

type ImportTodosApiTask = {
	task_title: string;
	priority: ImportTodoDraft["priority"];
	due: string | null;
	duration: string | null;
	description: string | null;
	source_file: string;
	source_file_index?: number;
	source_text: string;
	confidence: number;
};

type ImportTodosApiFileResult = {
	file_name: string;
	status: "success" | "failed";
	message: string | null;
	error_code: string | null;
};

type ImportTodosApiResponse = {
	file_results: ImportTodosApiFileResult[];
	extracted_tasks: ImportTodosApiTask[];
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

export function ChatInputSection({
	locale,
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
	const modeMenuRef = useRef<HTMLDivElement | null>(null);
	const fileInputRef = useRef<HTMLInputElement | null>(null);
	const filesRef = useRef<UploadFileItem[]>([]);
	const inputPlaceholder = tPage("chatInputPlaceholder");
	const { createTodo } = useTodoMutations();
	const [files, setFiles] = useState<UploadFileItem[]>([]);
	const [tasks, setTasks] = useState<ImportTodoDraft[]>([]);
	const [isUploading, setIsUploading] = useState(false);
	const [isCreating, setIsCreating] = useState(false);
	const [uploadError, setUploadError] = useState<string | null>(null);
	const [successMessage, setSuccessMessage] = useState<string | null>(null);

	useEffect(() => {
		filesRef.current = files;
	}, [files]);

	useEffect(() => {
		return () => {
			for (const file of filesRef.current) {
				if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
			}
		};
	}, []);

	const clearAll = useCallback(() => {
		for (const file of files) {
			if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
		}
		setFiles([]);
		setTasks([]);
		setUploadError(null);
		setSuccessMessage(null);
		if (fileInputRef.current) fileInputRef.current.value = "";
	}, [files]);

	const uploadFiles = useCallback(
		async (selectedFiles: File[]) => {
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
				status: "processing" as const,
				previewUrl: file.type.startsWith("image/")
					? URL.createObjectURL(file)
					: undefined,
			}));
			setFiles((current) => [...current, ...uploadItems]);
			setIsUploading(true);
			setUploadError(null);
			setSuccessMessage(null);

			const formData = new FormData();
			for (const file of selectedFiles) {
				formData.append("files", file);
			}
			formData.append("create_todos", "false");
			formData.append("reference_time", new Date().toISOString());

			try {
				const response = await fetch("/api/agent/import-todos", {
					method: "POST",
					body: formData,
				});
				if (!response.ok) {
					throw new Error(await parseApiError(response));
				}
				const data = (await response.json()) as ImportTodosApiResponse;
				const newTasks = data.extracted_tasks.map((task) => {
					const sourceFile =
						typeof task.source_file_index === "number"
							? uploadItems[task.source_file_index]
							: uploadItems.find((item) => item.name === task.source_file);
					return {
						id: makeClientId(),
						taskTitle: task.task_title,
						priority: task.priority,
						due: task.due,
						duration: task.duration,
						description: task.description,
						sourceFile: task.source_file,
						sourceFileId: sourceFile?.id ?? "",
						sourceText: task.source_text,
						confidence: task.confidence,
					};
				});

				setTasks((current) => [...current, ...newTasks]);
				if (newTasks.length === 0) {
					setUploadError(tImport("noTasksDetected"));
				}
				setFiles((current) =>
					current.map((item) => {
						const index = uploadItems.findIndex((upload) => upload.id === item.id);
						if (index === -1) return item;
						const result = data.file_results[index];
						return {
							...item,
							status: result?.status === "failed" ? "failed" : "processed",
							message:
								result?.message ||
								(result?.error_code ? result.error_code : tImport("processed")),
						};
					}),
				);
			} catch (uploadErr) {
				const message =
					uploadErr instanceof Error ? uploadErr.message : String(uploadErr);
				setUploadError(tImport("uploadFailed", { error: message }));
				setFiles((current) =>
					current.map((item) =>
						uploadItems.some((upload) => upload.id === item.id)
							? { ...item, status: "failed", message: tImport("failed") }
							: item,
					),
				);
			} finally {
				setIsUploading(false);
				if (fileInputRef.current) fileInputRef.current.value = "";
			}
		},
		[tImport],
	);

	const handleFileChange = useCallback(
		(event: React.ChangeEvent<HTMLInputElement>) => {
			void uploadFiles(Array.from(event.target.files ?? []));
		},
		[uploadFiles],
	);

	const removeFile = useCallback(
		(fileId: string) => {
			const target = files.find((file) => file.id === fileId);
			if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
			setFiles((current) => current.filter((file) => file.id !== fileId));
			if (target) {
				setTasks((current) =>
					current.filter((task) => task.sourceFileId !== target.id),
				);
			}
		},
		[files],
	);

	const updateTask = useCallback(
		(taskId: string, patch: Partial<ImportTodoDraft>) => {
			setTasks((current) =>
				current.map((task) => (task.id === taskId ? { ...task, ...patch } : task)),
			);
		},
		[],
	);

	const confirmCreate = useCallback(async () => {
		const validTasks = tasks.filter((task) => task.taskTitle.trim());
		if (validTasks.length === 0) {
			setUploadError(tImport("emptyTaskTitle"));
			return;
		}

		setIsCreating(true);
		setUploadError(null);
		const createdTaskIds = new Set<string>();
		try {
			for (const task of validTasks) {
				await createTodo({
					name: task.taskTitle.trim(),
					description: task.description ?? undefined,
					userNotes: [
						tImport("sourceFileNote", { file: task.sourceFile }),
						tImport("sourceTextNote", { text: task.sourceText }),
						tImport("confidenceNote", {
							value: Math.round(task.confidence * 100),
						}),
					].join("\n"),
					due: task.due ?? undefined,
					duration: task.duration ?? undefined,
					priority: task.priority,
					status: "draft",
					tags: ["文件导入", "AI解析"],
				});
				createdTaskIds.add(task.id);
			}
			for (const file of files) {
				if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
			}
			setFiles([]);
			setTasks([]);
			setUploadError(null);
			setSuccessMessage(tImport("createSuccess", { count: validTasks.length }));
			if (fileInputRef.current) fileInputRef.current.value = "";
		} catch (createErr) {
			const message =
				createErr instanceof Error ? createErr.message : String(createErr);
			if (createdTaskIds.size > 0) {
				setTasks((current) =>
					current.filter((task) => !createdTaskIds.has(task.id)),
				);
				setUploadError(
					tImport("createPartialFailed", {
						count: createdTaskIds.size,
						error: message,
					}),
				);
			} else {
				setUploadError(tImport("createFailed", { error: message }));
			}
		} finally {
			setIsCreating(false);
		}
	}, [createTodo, files, tImport, tasks]);

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
				tasks={tasks}
				isUploading={isUploading}
				isCreating={isCreating}
				successMessage={successMessage}
				errorMessage={uploadError}
				onRemoveFile={removeFile}
				onRemoveTask={(taskId) =>
					setTasks((current) => current.filter((task) => task.id !== taskId))
				}
				onUpdateTask={updateTask}
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
						<ToolSelector disabled={isStreaming} />
					</div>
				}
				inputValue={inputValue}
				placeholder={inputPlaceholder}
				isStreaming={isStreaming}
				locale={locale}
				uploadButton={
					<button
						type="button"
						onClick={() => fileInputRef.current?.click()}
						disabled={isStreaming || isUploading}
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
				onSend={onSend}
				onStop={onStop}
				onKeyDown={onKeyDown}
				onCompositionStart={onCompositionStart}
				onCompositionEnd={onCompositionEnd}
			/>

			{error && <p className="mt-2 text-sm">{error}</p>}
		</div>
	);
}

"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
	AlertTriangle,
	Check,
	Clock,
	Loader2,
	Paperclip,
	Send,
	Sparkles,
	X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	type AttachmentPlanDraft,
	ChatImportTodosPanel,
	type UploadFileItem,
} from "@/apps/chat/components/input/ChatImportTodosPanel";
import {
	type AttachmentPlanApiResponse,
	type AttachmentPlanConfirmResponse,
	type AttachmentPlanCreateMode,
	MAX_IMPORT_FILE_BYTES,
	MAX_IMPORT_FILES,
	makeClientId,
	parseApiError,
	revokePreviewUrls,
	SUPPORTED_IMPORT_ACCEPT,
	toApiTodo,
	toPlanDraft,
} from "@/apps/chat/utils/attachmentPlan";
import { customFetcher } from "@/lib/api/fetcher";
import { useCreateTodo } from "@/lib/query";
import { queryKeys } from "@/lib/query/keys";
import { toastError, toastSuccess } from "@/lib/toast";
import type { CreateTodoInput, TodoPriority } from "@/lib/types";
import { cn, getPriorityLabel } from "@/lib/utils";

interface NaturalLanguageTodoModalProps {
	isOpen: boolean;
	onClose: () => void;
}

interface AgentParseTaskResponse {
	taskTitle: string;
	priority: TodoPriority;
	due: string | null;
	duration: string | null;
	description: string | null;
	confidence: number;
	rawText: string;
	parseVersion: string;
}

const priorityOptions: TodoPriority[] = ["none", "low", "medium", "high"];

function toDateTimeLocal(value: string | null): string {
	if (!value) return "";
	return value.slice(0, 16);
}

function fromDateTimeLocal(value: string): string | undefined {
	if (!value) return undefined;
	const valueWithSeconds = value.length === 16 ? `${value}:00` : value;
	const utcTime = new Date(`${valueWithSeconds}+08:00`);
	if (Number.isNaN(utcTime.getTime())) return undefined;
	return utcTime.toISOString();
}

export function NaturalLanguageTodoModal({
	isOpen,
	onClose,
}: NaturalLanguageTodoModalProps) {
	const t = useTranslations("todoList");
	const tCommon = useTranslations("common");
	const tImport = useTranslations("chat.importTodos");
	const queryClient = useQueryClient();
	const createTodoMutation = useCreateTodo();
	const fileInputRef = useRef<HTMLInputElement | null>(null);
	const filesRef = useRef<UploadFileItem[]>([]);
	const planIdRef = useRef<string | null>(null);
	const promptAppliedRef = useRef(false);
	const [inputText, setInputText] = useState("");
	const [isParsing, setIsParsing] = useState(false);
	const [isPlanning, setIsPlanning] = useState(false);
	const [isCreatingPlan, setIsCreatingPlan] = useState(false);
	const [parseResult, setParseResult] = useState<AgentParseTaskResponse | null>(
		null,
	);
	const [files, setFiles] = useState<UploadFileItem[]>([]);
	const [planItems, setPlanItems] = useState<AttachmentPlanDraft[]>([]);
	const [planId, setPlanId] = useState<string | null>(null);
	const [uploadError, setUploadError] = useState<string | null>(null);
	const [successMessage, setSuccessMessage] = useState<string | null>(null);
	const [scheduleSummary, setScheduleSummary] = useState<string | null>(null);
	const [createMode, setCreateMode] =
		useState<AttachmentPlanCreateMode>("separate");
	const [parentTitle, setParentTitle] = useState("");
	const [taskTitle, setTaskTitle] = useState("");
	const [priority, setPriority] = useState<TodoPriority>("none");
	const [dueLocal, setDueLocal] = useState("");
	const [duration, setDuration] = useState("");
	const [description, setDescription] = useState("");

	useEffect(() => {
		filesRef.current = files;
	}, [files]);

	useEffect(() => {
		planIdRef.current = planId;
	}, [planId]);

	useEffect(() => {
		return () => {
			revokePreviewUrls(filesRef.current);
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

	const clearAttachmentState = useCallback(() => {
		revokePreviewUrls(filesRef.current);
		clearRemotePlan(planIdRef.current);
		setFiles([]);
		setPlanItems([]);
		setPlanId(null);
		setUploadError(null);
		setSuccessMessage(null);
		setScheduleSummary(null);
		setCreateMode("separate");
		setParentTitle("");
		promptAppliedRef.current = false;
		if (fileInputRef.current) fileInputRef.current.value = "";
	}, [clearRemotePlan]);

	const buildDefaultParentTitle = useCallback(
		(items: AttachmentPlanDraft[]) => {
			const firstTitle = items.find((item) => item.title.trim())?.title.trim();
			return firstTitle
				? tImport("defaultParentTitle", { title: firstTitle })
				: tImport("defaultParentTitleFallback");
		},
		[tImport],
	);

	const resetState = useCallback(() => {
		setInputText("");
		setParseResult(null);
		clearAttachmentState();
		setTaskTitle("");
		setPriority("none");
		setDueLocal("");
		setDuration("");
		setDescription("");
	}, [clearAttachmentState]);

	const handleClose = useCallback(() => {
		resetState();
		onClose();
	}, [onClose, resetState]);

	const appendDefaultPrompt = useCallback(
		(selectedFiles: File[]) => {
			if (promptAppliedRef.current) return;
			const prompt = tImport("promptTemplate", {
				files: selectedFiles.map((file) => file.name).join(", "),
			});
			const current = inputText.trim();
			setInputText(current ? `${inputText.trimEnd()}\n\n${prompt}` : prompt);
			promptAppliedRef.current = true;
		},
		[inputText, tImport],
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
			setParseResult(null);
			setUploadError(null);
			setSuccessMessage(null);
			setScheduleSummary(null);
			setCreateMode("separate");
			setParentTitle("");
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

	const removeFile = useCallback((fileId: string) => {
		const target = filesRef.current.find((file) => file.id === fileId);
		if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
		setFiles((current) => current.filter((file) => file.id !== fileId));
		if (typeof target?.sourceIndex === "number") {
			setPlanItems((current) =>
				current.filter(
					(item) => !item.sourceFileIndices.includes(target.sourceIndex ?? -1),
				),
			);
		}
	}, []);

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
		const prompt = inputText.trim();
		if (currentFiles.length === 0) return false;
		if (!prompt) {
			setUploadError(tImport("emptyPrompt"));
			return true;
		}

		setIsPlanning(true);
		setUploadError(null);
		setSuccessMessage(null);
		setScheduleSummary(null);
		setPlanItems([]);
		setParseResult(null);
		clearRemotePlan(planIdRef.current);
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
			setCreateMode(plannedItems.length > 1 ? "nested" : "separate");
			setParentTitle(
				plannedItems.length > 1 ? buildDefaultParentTitle(plannedItems) : "",
			);
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
		return true;
	}, [buildDefaultParentTitle, clearRemotePlan, inputText, tImport]);

	const submitTextPlan = useCallback(async () => {
		const prompt = inputText.trim();
		if (!prompt) {
			toastError(t("agentInputRequired"));
			return false;
		}

		setIsPlanning(true);
		setUploadError(null);
		setSuccessMessage(null);
		setScheduleSummary(null);
		setPlanItems([]);
		setParseResult(null);
		clearRemotePlan(planIdRef.current);
		setPlanId(null);

		try {
			const response = await fetch("/api/agent/text-plan", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					prompt,
					reference_time: new Date().toISOString(),
					planning_start: new Date().toISOString(),
				}),
			});
			if (!response.ok) {
				throw new Error(await parseApiError(response));
			}
			const data = (await response.json()) as AttachmentPlanApiResponse;
			const plannedItems = data.proposed_todos.map(toPlanDraft);
			setPlanId(data.plan_id);
			setPlanItems(plannedItems);
			setCreateMode(plannedItems.length > 1 ? "nested" : "separate");
			setParentTitle(
				plannedItems.length > 1 ? buildDefaultParentTitle(plannedItems) : "",
			);
			setScheduleSummary(data.schedule_summary || null);
			if (plannedItems.length === 0) {
				toastError(tImport("noPlanTodos"));
			} else {
				setSuccessMessage(tImport("planSuccess", { count: plannedItems.length }));
			}
			return true;
		} catch (planErr) {
			const message = planErr instanceof Error ? planErr.message : String(planErr);
			toastError(tImport("planFailed", { error: message }));
			return true;
		} finally {
			setIsPlanning(false);
		}
	}, [buildDefaultParentTitle, clearRemotePlan, inputText, t, tImport]);

	const confirmAttachmentCreate = useCallback(async () => {
		const validItems = planItems.filter((item) => item.title.trim());
		if (!planId || validItems.length === 0) {
			setUploadError(tImport("emptyTaskTitle"));
			return;
		}

		setIsCreatingPlan(true);
		setUploadError(null);
		try {
			const resolvedCreateMode =
				validItems.length > 1 ? createMode : "separate";
			const response = await fetch(
				`/api/agent/attachment-plan/${planId}/confirm`,
				{
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						proposed_todos: validItems.map(toApiTodo),
						create_mode: resolvedCreateMode,
						parent_title:
							resolvedCreateMode === "nested"
								? parentTitle.trim() || buildDefaultParentTitle(validItems)
								: null,
					}),
				},
			);
			if (!response.ok) {
				throw new Error(await parseApiError(response));
			}
			const data = (await response.json()) as AttachmentPlanConfirmResponse;
			toastSuccess(
				resolvedCreateMode === "nested"
					? tImport("createSuccessNested", {
							count: data.created_todos.filter(
								(todo) => todo.parent_todo_id != null,
							).length,
						})
					: tImport("createSuccess", { count: data.created_todos.length }),
			);
			void queryClient.invalidateQueries({ queryKey: queryKeys.todos.all });
			handleClose();
		} catch (createErr) {
			const message =
				createErr instanceof Error ? createErr.message : String(createErr);
			setUploadError(tImport("createFailed", { error: message }));
		} finally {
			setIsCreatingPlan(false);
		}
	}, [
		buildDefaultParentTitle,
		createMode,
		handleClose,
		parentTitle,
		planId,
		planItems,
		queryClient,
		tImport,
	]);

	const handleParse = async () => {
		const handledByAttachmentPlan = await submitAttachmentPlan();
		if (handledByAttachmentPlan) return;
		const handledByTextPlan = await submitTextPlan();
		if (handledByTextPlan) return;

		const text = inputText.trim();
		if (!text) {
			toastError(t("agentInputRequired"));
			return;
		}

		setIsParsing(true);
		try {
			const result = await customFetcher<AgentParseTaskResponse>(
				"/api/agent/parse-task",
				{
					method: "POST",
					data: {
						text,
						referenceTime: new Date().toISOString(),
					},
				},
			);
			setParseResult(result);
			setTaskTitle(result.taskTitle);
			setPriority(result.priority);
			setDueLocal(toDateTimeLocal(result.due));
			setDuration(result.duration ?? "");
			setDescription(result.description ?? "");
		} catch (error) {
			console.error("自然语言解析失败:", error);
			toastError(t("agentParseFailed"));
		} finally {
			setIsParsing(false);
		}
	};

	const handleCreate = async () => {
		if (!taskTitle.trim()) {
			toastError(t("agentTitleRequired"));
			return;
		}

		const userNotesParts = [
			parseResult?.rawText ? `${t("agentOriginalText")}: ${parseResult.rawText}` : "",
			parseResult?.parseVersion
				? `${t("agentParseVersion")}: ${parseResult.parseVersion}`
				: "",
		].filter(Boolean);

		const input: CreateTodoInput = {
			name: taskTitle.trim(),
			description: description.trim() || undefined,
			due: fromDateTimeLocal(dueLocal),
			duration: duration.trim() || undefined,
			priority,
			tags: [t("agentGeneratedTag")],
			userNotes: userNotesParts.length > 0 ? userNotesParts.join("\n") : undefined,
		};

		try {
			await createTodoMutation.mutateAsync(input);
			toastSuccess(t("agentCreateSuccess"));
			handleClose();
		} catch (error) {
			console.error("创建自然语言待办失败:", error);
			toastError(t("agentCreateFailed"));
		}
	};

	if (!isOpen) return null;

	return (
		<div
			role="button"
			tabIndex={0}
			className="fixed inset-0 z-[210] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
			onClick={handleClose}
			onKeyDown={(event) => {
				if (event.key === "Escape") {
					handleClose();
				}
			}}
		>
			<div
				role="dialog"
				aria-modal="true"
				aria-labelledby="natural-language-todo-title"
				className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-border bg-background shadow-xl"
				onClick={(event) => event.stopPropagation()}
				onKeyDown={(event) => {
					if (event.key === "Escape") {
						handleClose();
					}
				}}
			>
				<div className="flex items-center justify-between border-b border-border bg-muted/30 px-4 py-3">
					<div className="flex min-w-0 items-center gap-2">
						<Sparkles className="h-5 w-5 shrink-0 text-primary" />
						<h2
							id="natural-language-todo-title"
							className="truncate text-base font-semibold text-foreground"
						>
							{t("agentModalTitle")}
						</h2>
					</div>
					<button
						type="button"
						onClick={handleClose}
						className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
						aria-label={t("agentClose")}
					>
						<X className="h-5 w-5" />
					</button>
				</div>

				<div className="flex-1 overflow-y-auto p-4">
					<input
						ref={fileInputRef}
						type="file"
						multiple
						accept={SUPPORTED_IMPORT_ACCEPT}
						className="hidden"
						onChange={handleFileChange}
					/>
					<div className="space-y-4">
						<div className="space-y-2">
							<div className="flex items-center justify-between gap-3">
								<label
									htmlFor="agent-natural-language-input"
									className="text-sm font-medium text-foreground"
								>
									{files.length > 0
										? t("agentPlanPromptLabel")
										: t("agentInputLabel")}
								</label>
								<button
									type="button"
									onClick={() => fileInputRef.current?.click()}
									disabled={isParsing || isPlanning || isCreatingPlan}
									aria-label={t("agentAttachFiles")}
									className={cn(
										"inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors",
										"hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50",
									)}
								>
									<Paperclip className="h-3.5 w-3.5" />
									{t("agentAttachFiles")}
								</button>
							</div>
							<textarea
								id="agent-natural-language-input"
								value={inputText}
								onChange={(event) => setInputText(event.target.value)}
								placeholder={
									files.length > 0
										? t("agentPlanPromptPlaceholder")
										: t("agentInputPlaceholder")
								}
								className="min-h-[96px] w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
								maxLength={files.length > 0 ? 2000 : 500}
							/>
							<div className="flex items-center justify-between text-xs text-muted-foreground">
								<span>{inputText.length}/{files.length > 0 ? 2000 : 500}</span>
								<button
									type="button"
									onClick={handleParse}
									disabled={isParsing || isPlanning || !inputText.trim()}
									className={cn(
										"inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors",
										"hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50",
									)}
								>
									{isParsing || isPlanning ? (
										<Loader2 className="h-3.5 w-3.5 animate-spin" />
									) : (
										<Send className="h-3.5 w-3.5" />
									)}
									{files.length > 0 ? t("agentParseWithAttachments") : t("agentParse")}
								</button>
							</div>
						</div>

						<ChatImportTodosPanel
							files={files}
							planItems={planItems}
							isPlanning={isPlanning}
							isCreating={isCreatingPlan}
							successMessage={successMessage}
							errorMessage={uploadError}
							scheduleSummary={scheduleSummary}
							onRemoveFile={removeFile}
							onRemovePlanItem={(itemId) =>
								setPlanItems((current) =>
									current.filter((item) => item.id !== itemId),
								)
							}
							onUpdatePlanItem={updatePlanItem}
							onConfirmCreate={confirmAttachmentCreate}
							onClearAll={clearAttachmentState}
							createMode={createMode}
							parentTitle={parentTitle}
							onCreateModeChange={setCreateMode}
							onParentTitleChange={setParentTitle}
							showConfirmAction={false}
						/>

						{parseResult && (
							<div className="space-y-4 border-t border-border pt-4">
								<div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
									<span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1">
										<Clock className="h-3.5 w-3.5" />
										{t("agentConfidence", {
											value: Math.round(parseResult.confidence * 100),
										})}
									</span>
									{parseResult.confidence < 0.7 && (
										<span className="inline-flex items-center gap-1 rounded-md border border-amber-300/70 bg-amber-50 px-2 py-1 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
											<AlertTriangle className="h-3.5 w-3.5" />
											{t("agentLowConfidence")}
										</span>
									)}
								</div>

								<div className="grid gap-3 sm:grid-cols-2">
									<div className="space-y-1.5 sm:col-span-2">
										<label
											htmlFor="agent-task-title"
											className="text-xs font-medium text-muted-foreground"
										>
											{t("agentTitleLabel")}
										</label>
										<input
											id="agent-task-title"
											value={taskTitle}
											onChange={(event) => setTaskTitle(event.target.value)}
											className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
										/>
									</div>

									<div className="space-y-1.5">
										<label
											htmlFor="agent-priority"
											className="text-xs font-medium text-muted-foreground"
										>
											{t("priority")}
										</label>
										<select
											id="agent-priority"
											value={priority}
											onChange={(event) =>
												setPriority(event.target.value as TodoPriority)
											}
											className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
										>
											{priorityOptions.map((option) => (
												<option key={option} value={option}>
													{getPriorityLabel(option, tCommon)}
												</option>
											))}
										</select>
									</div>

									<div className="space-y-1.5">
										<label
											htmlFor="agent-due"
											className="text-xs font-medium text-muted-foreground"
										>
											{t("agentDueLabel")}
										</label>
										<input
											id="agent-due"
											type="datetime-local"
											value={dueLocal}
											onChange={(event) => setDueLocal(event.target.value)}
											className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
										/>
									</div>

									<div className="space-y-1.5 sm:col-span-2">
										<label
											htmlFor="agent-duration"
											className="text-xs font-medium text-muted-foreground"
										>
											{t("agentDurationLabel")}
										</label>
										<input
											id="agent-duration"
											value={duration}
											onChange={(event) => setDuration(event.target.value)}
											placeholder="PT2H"
											className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
										/>
									</div>

									<div className="space-y-1.5 sm:col-span-2">
										<label
											htmlFor="agent-description"
											className="text-xs font-medium text-muted-foreground"
										>
											{t("description")}
										</label>
										<textarea
											id="agent-description"
											value={description}
											onChange={(event) => setDescription(event.target.value)}
											className="min-h-[80px] w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
										/>
									</div>
								</div>
							</div>
						)}
					</div>
				</div>

				<div className="flex items-center justify-end gap-2 border-t border-border bg-muted/30 px-4 py-3">
					<button
						type="button"
						onClick={handleClose}
						className="rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
					>
						{t("agentCancel")}
					</button>
					<button
						type="button"
						onClick={planItems.length > 0 ? confirmAttachmentCreate : handleCreate}
						disabled={
							planItems.length > 0
								? isCreatingPlan
								: !parseResult || createTodoMutation.isPending
						}
						className={cn(
							"inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors",
							"hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50",
						)}
					>
						{createTodoMutation.isPending || isCreatingPlan ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							<Check className="h-4 w-4" />
						)}
						{planItems.length > 0
							? createMode === "nested" && planItems.length > 1
								? tImport("confirmCreateNested", { count: planItems.length })
								: tImport("confirmCreate", { count: planItems.length })
							: t("agentCreate")}
					</button>
				</div>
			</div>
		</div>
	);
}

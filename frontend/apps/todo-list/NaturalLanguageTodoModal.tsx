"use client";

import {
	AlertTriangle,
	Check,
	Clock,
	Loader2,
	Send,
	Sparkles,
	X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { customFetcher } from "@/lib/api/fetcher";
import { useCreateTodo } from "@/lib/query";
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
	const createTodoMutation = useCreateTodo();
	const [inputText, setInputText] = useState("");
	const [isParsing, setIsParsing] = useState(false);
	const [parseResult, setParseResult] = useState<AgentParseTaskResponse | null>(
		null,
	);
	const [taskTitle, setTaskTitle] = useState("");
	const [priority, setPriority] = useState<TodoPriority>("none");
	const [dueLocal, setDueLocal] = useState("");
	const [duration, setDuration] = useState("");
	const [description, setDescription] = useState("");

	const resetState = () => {
		setInputText("");
		setParseResult(null);
		setTaskTitle("");
		setPriority("none");
		setDueLocal("");
		setDuration("");
		setDescription("");
	};

	const handleClose = () => {
		resetState();
		onClose();
	};

	const handleParse = async () => {
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
					<div className="space-y-4">
						<div className="space-y-2">
							<label
								htmlFor="agent-natural-language-input"
								className="text-sm font-medium text-foreground"
							>
								{t("agentInputLabel")}
							</label>
							<textarea
								id="agent-natural-language-input"
								value={inputText}
								onChange={(event) => setInputText(event.target.value)}
								placeholder={t("agentInputPlaceholder")}
								className="min-h-[96px] w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
								maxLength={500}
							/>
							<div className="flex items-center justify-between text-xs text-muted-foreground">
								<span>{inputText.length}/500</span>
								<button
									type="button"
									onClick={handleParse}
									disabled={isParsing || !inputText.trim()}
									className={cn(
										"inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors",
										"hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50",
									)}
								>
									{isParsing ? (
										<Loader2 className="h-3.5 w-3.5 animate-spin" />
									) : (
										<Send className="h-3.5 w-3.5" />
									)}
									{t("agentParse")}
								</button>
							</div>
						</div>

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
						onClick={handleCreate}
						disabled={!parseResult || createTodoMutation.isPending}
						className={cn(
							"inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors",
							"hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50",
						)}
					>
						{createTodoMutation.isPending ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							<Check className="h-4 w-4" />
						)}
						{t("agentCreate")}
					</button>
				</div>
			</div>
		</div>
	);
}

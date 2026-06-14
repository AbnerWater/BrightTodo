"use client";

import {
	Check,
	FileText,
	GitBranch,
	Image as ImageIcon,
	ListChecks,
	Loader2,
	RefreshCw,
	Trash2,
	X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type React from "react";
import type { AttachmentPlanCreateMode } from "@/apps/chat/utils/attachmentPlan";
import type { TodoPriority } from "@/lib/types";
import { cn } from "@/lib/utils";

export type UploadFileItem = {
	id: string;
	name: string;
	type: string;
	size: number;
	status: "ready" | "planning" | "planned" | "failed";
	message?: string;
	rawTextPreview?: string | null;
	previewUrl?: string;
	sourceIndex?: number;
	file: File;
};

export type AttachmentPlanScheduleAlternative = {
	suggestedStart: string;
	suggestedEnd: string;
};

export type AttachmentPlanDraft = {
	id: string;
	planItemId: string;
	title: string;
	priority: TodoPriority;
	due: string | null;
	duration: string | null;
	description: string | null;
	suggestedStart: string | null;
	suggestedEnd: string | null;
	scheduleReason: string | null;
	scheduleAlternatives: AttachmentPlanScheduleAlternative[];
	sourceFileIndices: number[];
	sourceFiles: string[];
	sourceText: string | null;
	confidence: number;
};

type ChatImportTodosPanelProps = {
	files: UploadFileItem[];
	planItems: AttachmentPlanDraft[];
	isPlanning: boolean;
	isCreating: boolean;
	successMessage: string | null;
	errorMessage: string | null;
	scheduleSummary: string | null;
	onRemoveFile: (fileId: string) => void;
	onRemovePlanItem: (itemId: string) => void;
	onUpdatePlanItem: (itemId: string, patch: Partial<AttachmentPlanDraft>) => void;
	onUseAlternative?: (
		itemId: string,
		alternative: AttachmentPlanScheduleAlternative,
	) => void;
	onRetryPlan?: () => void;
	onConfirmCreate: () => void;
	onClearAll: () => void;
	createMode: AttachmentPlanCreateMode;
	parentTitle: string;
	onCreateModeChange: (mode: AttachmentPlanCreateMode) => void;
	onParentTitleChange: (title: string) => void;
	showConfirmAction?: boolean;
	className?: string;
};

const priorityOptions: TodoPriority[] = ["none", "low", "medium", "high"];

const formatFileSize = (size: number) => {
	if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
	if (size >= 1024) return `${Math.round(size / 1024)} KB`;
	return `${size} B`;
};

const toDateTimeLocalValue = (value: string | null) => {
	if (!value) return "";
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "";
	const pad = (num: number) => String(num).padStart(2, "0");
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const fromDateTimeLocalValue = (value: string) => {
	if (!value) return null;
	const date = new Date(value);
	return Number.isNaN(date.getTime()) ? null : date.toISOString();
};

const formatScheduleRange = (start: string, end: string) => {
	const startDate = new Date(start);
	const endDate = new Date(end);
	if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
		return `${start} - ${end}`;
	}
	const formatter = new Intl.DateTimeFormat("zh-CN", {
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
	return `${formatter.format(startDate)} - ${formatter.format(endDate)}`;
};

function FileStatusIcon({ file }: { file: UploadFileItem }) {
	if (file.status === "planning") {
		return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
	}
	if (file.status === "planned") {
		return <Check className="h-4 w-4 text-emerald-600" />;
	}
	if (file.type.startsWith("image/")) {
		return <ImageIcon className="h-4 w-4 text-muted-foreground" />;
	}
	return <FileText className="h-4 w-4 text-muted-foreground" />;
}

export function ChatImportTodosPanel({
	files,
	planItems,
	isPlanning,
	isCreating,
	successMessage,
	errorMessage,
	scheduleSummary,
	onRemoveFile,
	onRemovePlanItem,
	onUpdatePlanItem,
	onUseAlternative,
	onRetryPlan,
	onConfirmCreate,
	onClearAll,
	createMode,
	parentTitle,
	onCreateModeChange,
	onParentTitleChange,
	showConfirmAction = true,
	className,
}: ChatImportTodosPanelProps) {
	const t = useTranslations("chat.importTodos");
	const tPriority = useTranslations("common.priority");
	const hasContent =
		files.length > 0 ||
		planItems.length > 0 ||
		errorMessage ||
		successMessage ||
		scheduleSummary;

	if (!hasContent) return null;

	const showCreateModeSelector = planItems.length > 1;
	const isHeightConstrained = Boolean(className);
	const contentClassName = cn(
		isHeightConstrained
			? "min-h-0 flex-1 space-y-3 overflow-y-auto pr-1"
			: "space-y-3",
	);
	const createModeOptions: Array<{
		mode: AttachmentPlanCreateMode;
		icon: typeof ListChecks;
		label: string;
		description: string;
	}> = [
		{
			mode: "separate",
			icon: ListChecks,
			label: t("createModeSeparate"),
			description: t("createModeSeparateDesc"),
		},
		{
			mode: "nested",
			icon: GitBranch,
			label: t("createModeNested"),
			description: t("createModeNestedDesc"),
		},
	];

	return (
		<div
			className={cn(
				"mb-3 rounded-lg border border-border bg-background/80 p-3 shadow-sm",
				isHeightConstrained
					? "flex min-h-0 flex-col gap-3 overflow-hidden"
					: "space-y-3",
				className,
			)}
		>
			<div
				className={cn(
					"flex items-start justify-between gap-3",
					isHeightConstrained && "shrink-0",
				)}
			>
				<div>
					<p className="text-sm font-medium text-foreground">
						{planItems.length > 0 ? t("pendingTitle") : t("selectedFiles")}
					</p>
					<p className="mt-0.5 text-xs text-muted-foreground">
						{planItems.length > 0
							? t(files.length > 0 ? "pendingDesc" : "pendingTextDesc")
							: t("unsupportedHint")}
					</p>
				</div>
				<button
					type="button"
					onClick={onClearAll}
					className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-foreground/5"
					aria-label={t("clearAll")}
				>
					<X className="h-4 w-4" />
				</button>
			</div>

			{files.length > 0 && (
				<div
					className={cn(
						"grid gap-2 sm:grid-cols-2",
						isHeightConstrained && "shrink-0",
					)}
				>
					{files.map((file) => (
						<div
							key={file.id}
							className="flex min-w-0 items-center gap-2 rounded-md border border-border bg-muted/20 p-2"
						>
							{file.previewUrl ? (
								<div
									role="img"
									aria-label={t("imageAlt", { name: file.name })}
									className="h-10 w-10 shrink-0 rounded bg-cover bg-center"
									style={{ backgroundImage: `url(${file.previewUrl})` }}
								/>
							) : (
								<div className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-background">
									<FileStatusIcon file={file} />
								</div>
							)}
							<div className="min-w-0 flex-1">
								<p className="truncate text-xs font-medium text-foreground">
									{file.name}
								</p>
								<p className="truncate text-[11px] text-muted-foreground">
									{file.type || t("unknownType")} · {formatFileSize(file.size)}
								</p>
								{file.message && (
									<p className="truncate text-[11px] text-muted-foreground">
										{file.message}
									</p>
								)}
								{file.rawTextPreview && (
									<p className="truncate text-[11px] text-muted-foreground">
										{t("rawPreview", { text: file.rawTextPreview })}
									</p>
								)}
							</div>
							<FileStatusIcon file={file} />
							<button
								type="button"
								onClick={() => onRemoveFile(file.id)}
								disabled={isPlanning || isCreating}
								className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-foreground/5 disabled:cursor-not-allowed disabled:opacity-50"
								aria-label={t("removeFile")}
							>
								<X className="h-4 w-4" />
							</button>
						</div>
					))}
				</div>
			)}

			{isPlanning && (
				<div
					className={cn(
						"overflow-hidden rounded-full bg-muted",
						isHeightConstrained && "shrink-0",
					)}
				>
					<div className="h-1 w-1/2 animate-pulse rounded-full bg-primary" />
				</div>
			)}

			<div className={contentClassName}>
				{scheduleSummary && (
					<p className="rounded-md bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
						{scheduleSummary}
					</p>
				)}

				{showCreateModeSelector && (
					<div className="space-y-2 rounded-md border border-border bg-muted/20 p-2">
						<p className="text-xs font-medium text-foreground">
							{t("createModeLabel")}
						</p>
						<div className="grid gap-2 sm:grid-cols-2">
							{createModeOptions.map((option) => {
								const Icon = option.icon;
								const selected = createMode === option.mode;
								return (
									<button
										key={option.mode}
										type="button"
										onClick={() => onCreateModeChange(option.mode)}
										disabled={isPlanning || isCreating}
										className={cn(
											"flex items-start gap-2 rounded-md border p-2 text-left transition-colors",
											selected
												? "border-primary bg-primary/10 text-foreground"
												: "border-border bg-background text-muted-foreground hover:bg-muted",
											"disabled:cursor-not-allowed disabled:opacity-60",
										)}
										aria-pressed={selected}
									>
										<Icon className="mt-0.5 h-4 w-4 shrink-0" />
										<span className="min-w-0">
											<span className="block text-xs font-medium">
												{option.label}
											</span>
											<span className="mt-0.5 block text-[11px] leading-4">
												{option.description}
											</span>
										</span>
									</button>
								);
							})}
						</div>
						{createMode === "nested" && (
							<label className="block">
								<span className="mb-1 block text-[11px] text-muted-foreground">
									{t("parentTitleLabel")}
								</span>
								<input
									value={parentTitle}
									onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
										onParentTitleChange(event.target.value)
									}
									placeholder={t("parentTitlePlaceholder")}
									disabled={isPlanning || isCreating}
									className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
								/>
							</label>
						)}
					</div>
				)}

				{planItems.length > 0 && (
					<div
						className={cn(
							"space-y-2",
							!isHeightConstrained && "max-h-96 overflow-y-auto pr-1",
						)}
					>
						{planItems.map((item) => (
							<div
								key={item.id}
								className="grid gap-2 rounded-md border border-border bg-background p-2"
							>
								<div className="flex items-start gap-2">
									<label className="min-w-0 flex-1">
										<span className="sr-only">{t("taskTitleLabel")}</span>
										<input
											value={item.title}
											onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
												onUpdatePlanItem(item.id, { title: event.target.value })
											}
											placeholder={t("taskTitlePlaceholder")}
											className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
										/>
									</label>
									<button
										type="button"
										onClick={() => onRemovePlanItem(item.id)}
										className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-foreground/5"
										aria-label={t("removeTask")}
									>
										<Trash2 className="h-4 w-4" />
									</button>
								</div>
								<div className="grid gap-2 sm:grid-cols-3">
									<label className="min-w-0">
										<span className="mb-1 block text-[11px] text-muted-foreground">
											{t("dueLabel")}
										</span>
										<input
											type="datetime-local"
											value={toDateTimeLocalValue(item.due)}
											onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
												onUpdatePlanItem(item.id, {
													due: fromDateTimeLocalValue(event.target.value),
												})
											}
											className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
										/>
									</label>
									<label>
										<span className="mb-1 block text-[11px] text-muted-foreground">
											{t("priorityLabel")}
										</span>
										<select
											value={item.priority}
											onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
												onUpdatePlanItem(item.id, {
													priority: event.target.value as TodoPriority,
												})
											}
											className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
										>
											{priorityOptions.map((priority) => (
												<option key={priority} value={priority}>
													{tPriority(priority)}
												</option>
											))}
										</select>
									</label>
									<label>
										<span className="mb-1 block text-[11px] text-muted-foreground">
											{t("durationLabel")}
										</span>
										<input
											value={item.duration ?? ""}
											onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
												onUpdatePlanItem(item.id, {
													duration: event.target.value || null,
												})
											}
											placeholder="PT1H"
											className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
										/>
									</label>
								</div>
								<div className="grid gap-2 sm:grid-cols-2">
									<label className="min-w-0">
										<span className="mb-1 block text-[11px] text-muted-foreground">
											{t("suggestedStartLabel")}
										</span>
										<input
											type="datetime-local"
											value={toDateTimeLocalValue(item.suggestedStart)}
											onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
												onUpdatePlanItem(item.id, {
													suggestedStart: fromDateTimeLocalValue(
														event.target.value,
													),
												})
											}
											className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
										/>
									</label>
									<label className="min-w-0">
										<span className="mb-1 block text-[11px] text-muted-foreground">
											{t("suggestedEndLabel")}
										</span>
										<input
											type="datetime-local"
											value={toDateTimeLocalValue(item.suggestedEnd)}
											onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
												onUpdatePlanItem(item.id, {
													suggestedEnd: fromDateTimeLocalValue(
														event.target.value,
													),
												})
											}
											className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
										/>
									</label>
								</div>
								<label>
									<span className="mb-1 block text-[11px] text-muted-foreground">
										{t("descriptionLabel")}
									</span>
									<textarea
										value={item.description ?? ""}
										onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) =>
											onUpdatePlanItem(item.id, {
												description: event.target.value || null,
											})
										}
										rows={2}
										className="w-full resize-none rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
									/>
								</label>
								<p className="line-clamp-2 text-[11px] text-muted-foreground">
									{item.sourceFiles.join(", ") || t("unknownType")}
									{item.sourceText ? ` · ${item.sourceText}` : ""}
								</p>
								{item.scheduleReason && (
									<p className="text-[11px] text-muted-foreground">
										{item.scheduleReason}
									</p>
								)}
								{!item.suggestedStart && !item.scheduleReason && (
									<p className="text-[11px] text-amber-600 dark:text-amber-300">
										{t("unscheduledHint")}
									</p>
								)}
								{item.scheduleAlternatives.length > 0 && (
									<div className="flex flex-wrap items-center gap-1.5">
										<span className="text-[11px] text-muted-foreground">
											{t("alternativesLabel")}
										</span>
										{item.scheduleAlternatives.map((alternative) => (
											<button
												key={`${alternative.suggestedStart}-${alternative.suggestedEnd}`}
												type="button"
												onClick={() =>
													onUseAlternative?.(item.id, alternative)
												}
												disabled={isPlanning || isCreating || !onUseAlternative}
												className="rounded-md border border-border px-2 py-1 text-[11px] text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
											>
												{t("useAlternative", {
													time: formatScheduleRange(
														alternative.suggestedStart,
														alternative.suggestedEnd,
													),
												})}
											</button>
										))}
									</div>
								)}
							</div>
						))}
					</div>
				)}

				{errorMessage && (
					<div className="flex flex-wrap items-center justify-between gap-2">
						<p className="min-w-0 text-xs text-destructive">{errorMessage}</p>
						{onRetryPlan && (
							<button
								type="button"
								onClick={onRetryPlan}
								disabled={isPlanning || isCreating}
								className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border px-2 text-xs text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
							>
								<RefreshCw className="h-3.5 w-3.5" />
								{t("retryPlan")}
							</button>
						)}
					</div>
				)}
				{successMessage && (
					<p className="text-xs text-emerald-600">{successMessage}</p>
				)}
			</div>

			{showConfirmAction && planItems.length > 0 && (
				<div
					className={cn(
						isHeightConstrained
							? "shrink-0 border-t border-border/70 pt-2"
							: "flex items-center justify-end",
					)}
				>
					<div
						className={cn(isHeightConstrained && "flex items-center justify-end")}
					>
						<button
							type="button"
							onClick={onConfirmCreate}
							disabled={isCreating}
							className={cn(
								"inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground",
								"hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60",
							)}
						>
							{isCreating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
							{isCreating
								? t("creating")
								: createMode === "nested" && planItems.length > 1
									? t("confirmCreateNested", { count: planItems.length })
									: t("confirmCreate", { count: planItems.length })}
						</button>
					</div>
				</div>
			)}
		</div>
	);
}

"use client";

import {
	Check,
	FileText,
	Image as ImageIcon,
	Loader2,
	Trash2,
	X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type React from "react";
import type { TodoPriority } from "@/lib/types";
import { cn } from "@/lib/utils";

export type UploadFileItem = {
	id: string;
	name: string;
	type: string;
	size: number;
	status: "ready" | "planning" | "planned" | "failed";
	message?: string;
	previewUrl?: string;
	sourceIndex?: number;
	file: File;
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
	onConfirmCreate: () => void;
	onClearAll: () => void;
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
	onConfirmCreate,
	onClearAll,
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

	return (
		<div className="mb-3 space-y-3 rounded-lg border border-border bg-background/80 p-3 shadow-sm">
			<div className="flex items-start justify-between gap-3">
				<div>
					<p className="text-sm font-medium text-foreground">
						{planItems.length > 0 ? t("pendingTitle") : t("selectedFiles")}
					</p>
					<p className="mt-0.5 text-xs text-muted-foreground">
						{planItems.length > 0 ? t("pendingDesc") : t("unsupportedHint")}
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
				<div className="grid gap-2 sm:grid-cols-2">
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
				<div className="overflow-hidden rounded-full bg-muted">
					<div className="h-1 w-1/2 animate-pulse rounded-full bg-primary" />
				</div>
			)}

			{scheduleSummary && (
				<p className="rounded-md bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
					{scheduleSummary}
				</p>
			)}

			{planItems.length > 0 && (
				<div className="max-h-96 space-y-2 overflow-y-auto pr-1">
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
						</div>
					))}
				</div>
			)}

			{errorMessage && (
				<p className="text-xs text-destructive">{errorMessage}</p>
			)}
			{successMessage && (
				<p className="text-xs text-emerald-600">{successMessage}</p>
			)}

			{planItems.length > 0 && (
				<div className="flex items-center justify-end">
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
							: t("confirmCreate", { count: planItems.length })}
					</button>
				</div>
			)}
		</div>
	);
}

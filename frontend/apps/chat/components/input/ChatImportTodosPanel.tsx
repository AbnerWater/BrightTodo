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
	status: "ready" | "processing" | "processed" | "failed";
	message?: string;
	previewUrl?: string;
};

export type ImportTodoDraft = {
	id: string;
	taskTitle: string;
	priority: TodoPriority;
	due: string | null;
	duration: string | null;
	description: string | null;
	sourceFile: string;
	sourceFileId: string;
	sourceText: string;
	confidence: number;
};

type ChatImportTodosPanelProps = {
	files: UploadFileItem[];
	tasks: ImportTodoDraft[];
	isUploading: boolean;
	isCreating: boolean;
	successMessage: string | null;
	errorMessage: string | null;
	onRemoveFile: (fileId: string) => void;
	onRemoveTask: (taskId: string) => void;
	onUpdateTask: (taskId: string, patch: Partial<ImportTodoDraft>) => void;
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
	if (file.status === "processing") {
		return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
	}
	if (file.status === "processed") {
		return <Check className="h-4 w-4 text-emerald-600" />;
	}
	if (file.type.startsWith("image/")) {
		return <ImageIcon className="h-4 w-4 text-muted-foreground" />;
	}
	return <FileText className="h-4 w-4 text-muted-foreground" />;
}

export function ChatImportTodosPanel({
	files,
	tasks,
	isUploading,
	isCreating,
	successMessage,
	errorMessage,
	onRemoveFile,
	onRemoveTask,
	onUpdateTask,
	onConfirmCreate,
	onClearAll,
}: ChatImportTodosPanelProps) {
	const t = useTranslations("chat.importTodos");
	const tPriority = useTranslations("common.priority");
	const hasContent = files.length > 0 || tasks.length > 0 || errorMessage || successMessage;

	if (!hasContent) return null;

	return (
		<div className="mb-3 space-y-3 rounded-lg border border-border bg-background/80 p-3 shadow-sm">
			<div className="flex items-start justify-between gap-3">
				<div>
					<p className="text-sm font-medium text-foreground">
						{tasks.length > 0 ? t("pendingTitle") : t("selectedFiles")}
					</p>
					<p className="mt-0.5 text-xs text-muted-foreground">
						{tasks.length > 0 ? t("pendingDesc") : t("unsupportedHint")}
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
								className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-foreground/5"
								aria-label={t("removeFile")}
							>
								<X className="h-4 w-4" />
							</button>
						</div>
					))}
				</div>
			)}

			{isUploading && (
				<div className="overflow-hidden rounded-full bg-muted">
					<div className="h-1 w-1/2 animate-pulse rounded-full bg-primary" />
				</div>
			)}

			{tasks.length > 0 && (
				<div className="max-h-72 space-y-2 overflow-y-auto pr-1">
					{tasks.map((task) => (
						<div
							key={task.id}
							className="grid gap-2 rounded-md border border-border bg-background p-2"
						>
							<div className="flex items-start gap-2">
								<label className="min-w-0 flex-1">
									<span className="sr-only">{t("taskTitleLabel")}</span>
									<input
										value={task.taskTitle}
										onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
											onUpdateTask(task.id, { taskTitle: event.target.value })
										}
										placeholder={t("taskTitlePlaceholder")}
										className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
									/>
								</label>
								<button
									type="button"
									onClick={() => onRemoveTask(task.id)}
									className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-foreground/5"
									aria-label={t("removeTask")}
								>
									<Trash2 className="h-4 w-4" />
								</button>
							</div>
							<div className="grid gap-2 sm:grid-cols-2">
								<label className="min-w-0">
									<span className="mb-1 block text-[11px] text-muted-foreground">
										{t("dueLabel")}
									</span>
									<input
										type="datetime-local"
										value={toDateTimeLocalValue(task.due)}
										onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
											onUpdateTask(task.id, {
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
										value={task.priority}
										onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
											onUpdateTask(task.id, {
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
							</div>
							<p className="line-clamp-2 text-[11px] text-muted-foreground">
								{task.sourceFile} · {task.sourceText}
							</p>
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

			{tasks.length > 0 && (
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
						{isCreating ? t("creating") : t("confirmCreate", { count: tasks.length })}
					</button>
				</div>
			)}
		</div>
	);
}

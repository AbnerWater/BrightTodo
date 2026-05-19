"use client";

import {
	FileUp,
	FolderOpen,
	GripVertical,
	ImageIcon,
	NotebookText,
	Paperclip,
	Trash2,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getAttachmentFileUrl, MAX_ATTACHMENT_SIZE_BYTES } from "@/lib/attachments";
import { toastError } from "@/lib/toast";
import type { Todo, TodoAttachment } from "@/lib/types";

interface ArtifactsViewProps {
	todo: Todo;
	attachments: TodoAttachment[];
	onUpload: (files: File[]) => void;
	onRemove: (attachmentId: number) => void;
	onSelectAttachment: (attachment: TodoAttachment) => void;
	onShowDetail: () => void;
}

const formatBytes = (value?: number) => {
	if (!value && value !== 0) return "—";
	const units = ["B", "KB", "MB", "GB"];
	let size = value;
	let unitIndex = 0;
	while (size >= 1024 && unitIndex < units.length - 1) {
		size /= 1024;
		unitIndex += 1;
	}
	return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
};

export function ArtifactsView({
	todo,
	attachments,
	onUpload,
	onRemove,
	onSelectAttachment,
	onShowDetail,
}: ArtifactsViewProps) {
	const t = useTranslations("todoDetail");
	const uploadInputRef = useRef<HTMLInputElement | null>(null);

	const { artifacts, contextAttachments } = useMemo(() => {
		const artifactsList: TodoAttachment[] = [];
		const contextList: TodoAttachment[] = [];
		for (const attachment of attachments) {
			if (attachment.source === "ai") {
				artifactsList.push(attachment);
			} else {
				contextList.push(attachment);
			}
		}
		return { artifacts: artifactsList, contextAttachments: contextList };
	}, [attachments]);

	const handleSelectFiles = (event: ChangeEvent<HTMLInputElement>) => {
		const files = Array.from(event.target.files || []);
		if (files.length === 0) return;

		const oversized = files.find((file) => file.size > MAX_ATTACHMENT_SIZE_BYTES);
		if (oversized) {
			toastError(t("uploadSizeLimit"));
			event.target.value = "";
			return;
		}

		onUpload(files);
		event.target.value = "";
	};

	const renderAttachmentRow = (attachment: TodoAttachment) => {
		return (
			<div
				key={attachment.id}
				className="flex items-center gap-3 rounded-md border border-border bg-background px-3 py-2 text-xs"
			>
				<div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted/40">
					{attachment.mimeType?.startsWith("image/") ? (
						<ImageIcon className="h-4 w-4 text-muted-foreground" />
					) : (
						<Paperclip className="h-4 w-4 text-muted-foreground" />
					)}
				</div>
				<div className="flex-1 truncate">
					<div className="truncate text-sm font-medium text-foreground">
						{attachment.fileName}
					</div>
					<div className="flex items-center gap-2 text-xs text-muted-foreground">
						<span>{attachment.mimeType || "unknown"}</span>
						<span>•</span>
						<span>{formatBytes(attachment.fileSize)}</span>
					</div>
				</div>
				<button
					type="button"
					onClick={() => onSelectAttachment(attachment)}
					className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
				>
					{t("previewLabel")}
				</button>
				<a
					href={getAttachmentFileUrl(attachment.id)}
					target="_blank"
					rel="noreferrer"
					className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
				>
					{t("downloadLabel")}
				</a>
				<button
					type="button"
					onClick={() => onRemove(attachment.id)}
					className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
				>
					<Trash2 className="h-3.5 w-3.5" />
				</button>
			</div>
		);
	};

	return (
		<div className="flex min-w-0 flex-1 flex-col gap-6">
			<section className="rounded-xl border border-border bg-muted/20 px-4 py-4">
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						<GripVertical className="h-4 w-4" />
						<span>{t("progressLabel")}</span>
					</div>
				</div>
				<div className="mt-3 space-y-2 text-sm text-muted-foreground">
					<p>{t("progressEmptyTitle")}</p>
					<p className="text-xs">{t("progressEmptyHint")}</p>
				</div>
			</section>

			<section className="rounded-xl border border-border bg-background px-4 py-4">
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						<FolderOpen className="h-4 w-4" />
						<span>{t("artifactsLabel")}</span>
					</div>
				</div>
				<div className="mt-4 space-y-2">
					{artifacts.length === 0 ? (
						<div className="rounded-md border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
							{t("artifactsEmpty")}
						</div>
					) : (
						artifacts.map(renderAttachmentRow)
					)}
				</div>
			</section>

			<section className="rounded-xl border border-border bg-background px-4 py-4">
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						<NotebookText className="h-4 w-4" />
						<span>{t("contextLabel")}</span>
					</div>
					<button
						type="button"
						onClick={onShowDetail}
						className="text-xs text-muted-foreground hover:text-foreground transition-colors"
					>
						{t("editContext")}
					</button>
				</div>

				<div className="mt-4 grid gap-4">
					<div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
						<div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
							{t("backgroundLabel")}
						</div>
						{todo.description ? (
							<div className="text-sm text-foreground markdown-content">
								<ReactMarkdown remarkPlugins={[remarkGfm]}>
									{todo.description}
								</ReactMarkdown>
							</div>
						) : (
							<p className="text-sm text-muted-foreground">
								{t("backgroundEmptyPlaceholder")}
							</p>
						)}
					</div>
					<div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
						<div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
							{t("notesLabel")}
						</div>
						{todo.userNotes ? (
							<div className="text-sm text-foreground markdown-content">
								<ReactMarkdown remarkPlugins={[remarkGfm]}>
									{todo.userNotes}
								</ReactMarkdown>
							</div>
						) : (
							<p className="text-sm text-muted-foreground">
								{t("notesEmptyPlaceholder")}
							</p>
						)}
					</div>

					<div className="rounded-lg border border-border bg-muted/10 px-3 py-3">
						<div className="mb-3 flex items-center justify-between">
							<div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
								<Paperclip className="h-4 w-4" />
								<span>{t("contextAttachmentsLabel")}</span>
							</div>
							<input
								ref={uploadInputRef}
								type="file"
								multiple
								className="hidden"
								onChange={handleSelectFiles}
							/>
							<button
								type="button"
								onClick={() => uploadInputRef.current?.click()}
								className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
							>
								<FileUp className="h-3.5 w-3.5" />
								{t("uploadLabel")}
							</button>
						</div>
						{contextAttachments.length === 0 ? (
							<div className="rounded-md border border-dashed border-border bg-background px-4 py-4 text-center text-sm text-muted-foreground">
								{t("contextAttachmentsEmpty")}
							</div>
						) : (
							<div className="space-y-2">
								{contextAttachments.map(renderAttachmentRow)}
							</div>
						)}
						<p className="mt-2 text-xs text-muted-foreground">
							{t("uploadHint")}
						</p>
					</div>
				</div>
			</section>
		</div>
	);
}

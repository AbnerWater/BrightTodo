import type {
	AttachmentPlanDraft,
	UploadFileItem,
} from "@/apps/chat/components/input/ChatImportTodosPanel";
import type { TodoPriority } from "@/lib/types";

export type AttachmentPlanCreateMode = "separate" | "nested";

export type AttachmentPlanApiFileResult = {
	file_name: string;
	status: "ready" | "failed";
	message: string | null;
	error_code: string | null;
};

export type AttachmentPlanApiTodo = {
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

export type AttachmentPlanApiResponse = {
	plan_id: string;
	file_results: AttachmentPlanApiFileResult[];
	proposed_todos: AttachmentPlanApiTodo[];
	schedule_summary: string;
};

export type AttachmentPlanConfirmResponse = {
	created_todos: Array<{
		id: number;
		name: string;
		status: string;
		parent_todo_id?: number | null;
		attachment_ids?: number[];
	}>;
};

export const SUPPORTED_IMPORT_ACCEPT = [
	".png",
	".jpg",
	".jpeg",
	".webp",
	".txt",
	".md",
	".markdown",
	".csv",
	".json",
	".pdf",
	".docx",
	".xlsx",
	".xlsm",
	".xltx",
	".xltm",
	".xls",
	".pptx",
	".pptm",
	".ppsx",
	".ppsm",
	".potx",
	".potm",
	".ppt",
].join(",");
export const MAX_IMPORT_FILES = 5;
export const MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024;

export const makeClientId = () =>
	typeof crypto !== "undefined" && "randomUUID" in crypto
		? crypto.randomUUID()
		: `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const parseApiError = async (response: Response) => {
	try {
		const data = (await response.json()) as { message?: string; detail?: string };
		return data.message || data.detail || `HTTP ${response.status}`;
	} catch {
		return `HTTP ${response.status}`;
	}
};

export const toPlanDraft = (
	todo: AttachmentPlanApiTodo,
): AttachmentPlanDraft => ({
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

export const toApiTodo = (
	item: AttachmentPlanDraft,
): AttachmentPlanApiTodo => ({
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

export const revokePreviewUrls = (files: UploadFileItem[]) => {
	for (const file of files) {
		if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
	}
};

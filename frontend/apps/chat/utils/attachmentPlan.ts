import type {
	AttachmentPlanDraft,
	UploadFileItem,
} from "@/apps/chat/components/input/ChatImportTodosPanel";
import type { Todo, TodoPriority } from "@/lib/types";

export type AttachmentPlanCreateMode = "separate" | "nested";

export type AttachmentPlanApiFileResult = {
	file_name: string;
	status: "ready" | "failed";
	message: string | null;
	error_code: string | null;
	raw_text_preview: string | null;
};

export type AttachmentPlanApiScheduleAlternative = {
	suggested_start: string;
	suggested_end: string;
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
	schedule_alternatives: AttachmentPlanApiScheduleAlternative[];
	source_file_indices: number[];
	source_files: string[];
	source_text: string | null;
	confidence: number;
};

export type ScheduleBlockedSlot = {
	start: string;
	end: string;
	label?: string | null;
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
	scheduleAlternatives: (todo.schedule_alternatives ?? []).map(
		(alternative) => ({
			suggestedStart: alternative.suggested_start,
			suggestedEnd: alternative.suggested_end,
		}),
	),
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
	schedule_alternatives: (item.scheduleAlternatives ?? []).map((alternative) => ({
		suggested_start: alternative.suggestedStart,
		suggested_end: alternative.suggestedEnd,
	})),
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

const DEFAULT_PLANNING_WINDOW_DAYS = 7;
const MAX_BLOCKED_SLOTS = 100;
const WEEKDAY_MAP: Record<string, number> = {
	SU: 0,
	MO: 1,
	TU: 2,
	WE: 3,
	TH: 4,
	FR: 5,
	SA: 6,
};

const parseDate = (value?: string | null) => {
	if (!value) return null;
	const date = new Date(value);
	return Number.isNaN(date.getTime()) ? null : date;
};

const addDays = (date: Date, days: number) => {
	const next = new Date(date);
	next.setDate(next.getDate() + days);
	return next;
};

const overlapsWindow = (start: Date, end: Date, windowStart: Date, windowEnd: Date) =>
	start < windowEnd && end > windowStart;

const parseWeeklyDays = (rrule: string | null | undefined, fallback: Date) => {
	if (!rrule) return [fallback.getDay()];
	const byDay = rrule
		.toUpperCase()
		.split(";")
		.find((part) => part.startsWith("BYDAY="))
		?.replace("BYDAY=", "");
	if (!byDay) return [fallback.getDay()];
	const days = byDay
		.split(",")
		.map((day) => WEEKDAY_MAP[day.trim()])
		.filter((day): day is number => typeof day === "number");
	return days.length > 0 ? days : [fallback.getDay()];
};

const createDateWithTime = (source: Date, targetDate: Date) => {
	const next = new Date(targetDate);
	next.setHours(
		source.getHours(),
		source.getMinutes(),
		source.getSeconds(),
		source.getMilliseconds(),
	);
	return next;
};

const toBlockedSlot = (
	todo: Todo,
	start: Date,
	end: Date,
): ScheduleBlockedSlot => ({
	start: start.toISOString(),
	end: end.toISOString(),
	label: todo.name ? `已有待办：${todo.name}` : null,
});

export const buildBlockedSlotsFromTodos = (
	todos: Todo[],
	windowStart = new Date(),
	windowEnd = addDays(windowStart, DEFAULT_PLANNING_WINDOW_DAYS),
): ScheduleBlockedSlot[] => {
	const slots: ScheduleBlockedSlot[] = [];

	for (const todo of todos) {
		if (todo.status === "completed" || todo.status === "canceled") continue;
		const start = parseDate(todo.startTime ?? todo.dtstart);
		const end = parseDate(todo.endTime ?? todo.dtend);
		if (!start || !end || end <= start) continue;

		if (!todo.rrule?.toUpperCase().includes("FREQ=WEEKLY")) {
			if (overlapsWindow(start, end, windowStart, windowEnd)) {
				slots.push(toBlockedSlot(todo, start, end));
			}
			continue;
		}

		const durationMs = end.getTime() - start.getTime();
		const weekdays = parseWeeklyDays(todo.rrule, start);
		for (
			let day = new Date(windowStart);
			day < windowEnd && slots.length < MAX_BLOCKED_SLOTS;
			day = addDays(day, 1)
		) {
			if (!weekdays.includes(day.getDay())) continue;
			const occurrenceStart = createDateWithTime(start, day);
			const occurrenceEnd = new Date(occurrenceStart.getTime() + durationMs);
			if (overlapsWindow(occurrenceStart, occurrenceEnd, windowStart, windowEnd)) {
				slots.push(toBlockedSlot(todo, occurrenceStart, occurrenceEnd));
			}
		}

		if (slots.length >= MAX_BLOCKED_SLOTS) break;
	}

	return slots.slice(0, MAX_BLOCKED_SLOTS);
};

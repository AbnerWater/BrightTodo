"use client";

import type { Todo, TodoPriority } from "@/lib/types";

export type ScheduleBlockedSlot = {
	start: string;
	end: string;
	label?: string | null;
};

export type ScheduleHintConflict = ScheduleBlockedSlot;

export type ScheduleHintOption = {
	suggestedStart: string;
	suggestedEnd: string;
};

export type CreateScheduleSuggestion = ScheduleHintOption & {
	reason: string;
	alternatives: ScheduleHintOption[];
};

export type CreateScheduleSuggestionInput = {
	title: string;
	priority?: TodoPriority;
	due?: string | null;
	duration?: string | null;
	planningStart?: Date | string | null;
	planningEnd?: Date | string | null;
	blockedSlots: ScheduleBlockedSlot[];
};

type ApiScheduleAlternative = {
	suggested_start?: string;
	suggested_end?: string;
	suggestedStart?: string;
	suggestedEnd?: string;
};

type ApiScheduleSuggestion = ApiScheduleAlternative & {
	reason?: string;
	alternatives?: ApiScheduleAlternative[];
};

type ApiScheduleSuggestResponse = {
	suggestions?: ApiScheduleSuggestion[];
};

export const DEFAULT_CREATE_DURATION = "PT1H";
export const DEFAULT_PLANNING_WINDOW_DAYS = 7;
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

export const addDays = (date: Date, days: number) => {
	const next = new Date(date);
	next.setDate(next.getDate() + days);
	return next;
};

const parseDate = (value?: string | null) => {
	if (!value) return null;
	const date = new Date(value);
	return Number.isNaN(date.getTime()) ? null : date;
};

const toDate = (value: Date | string | null | undefined) => {
	if (!value) return null;
	if (value instanceof Date) {
		return Number.isNaN(value.getTime()) ? null : value;
	}
	return parseDate(value);
};

const overlapsWindow = (
	start: Date,
	end: Date,
	windowStart: Date,
	windowEnd: Date,
) => start < windowEnd && end > windowStart;

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

export const findScheduleConflicts = (
	start: string | null | undefined,
	end: string | null | undefined,
	blockedSlots: ScheduleBlockedSlot[],
): ScheduleHintConflict[] => {
	const startDate = parseDate(start);
	const endDate = parseDate(end);
	if (!startDate || !endDate || endDate <= startDate) return [];

	return blockedSlots.filter((slot) => {
		const blockedStart = parseDate(slot.start);
		const blockedEnd = parseDate(slot.end);
		if (!blockedStart || !blockedEnd || blockedEnd <= blockedStart) return false;
		return startDate < blockedEnd && endDate > blockedStart;
	});
};

export const toDateTimeLocalInputValue = (value: string | null | undefined) => {
	const date = parseDate(value);
	if (!date) return "";
	const pad = (num: number) => String(num).padStart(2, "0");
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export const fromDateTimeLocalInputValue = (value: string) => {
	if (!value) return null;
	const date = new Date(value);
	return Number.isNaN(date.getTime()) ? null : date.toISOString();
};

export const minutesToIsoDuration = (minutes: number) => {
	if (!Number.isFinite(minutes) || minutes <= 0) return DEFAULT_CREATE_DURATION;
	const rounded = Math.max(1, Math.round(minutes));
	const hours = Math.floor(rounded / 60);
	const restMinutes = rounded % 60;
	if (hours > 0 && restMinutes > 0) return `PT${hours}H${restMinutes}M`;
	if (hours > 0) return `PT${hours}H`;
	return `PT${restMinutes}M`;
};

export const isoDurationFromRange = (
	start: string | null | undefined,
	end: string | null | undefined,
) => {
	const startDate = parseDate(start);
	const endDate = parseDate(end);
	if (!startDate || !endDate || endDate <= startDate) return DEFAULT_CREATE_DURATION;
	return minutesToIsoDuration((endDate.getTime() - startDate.getTime()) / 60000);
};

export const formatScheduleRange = (
	start: string | null | undefined,
	end: string | null | undefined,
	locale = "zh-CN",
) => {
	const startDate = parseDate(start);
	const endDate = parseDate(end);
	if (!startDate || !endDate) {
		return `${start ?? ""} - ${end ?? ""}`.trim();
	}
	const formatter = new Intl.DateTimeFormat(locale, {
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
	return `${formatter.format(startDate)} - ${formatter.format(endDate)}`;
};

const parseApiError = async (response: Response) => {
	try {
		const data = (await response.json()) as { message?: string; detail?: string };
		return data.message || data.detail || `HTTP ${response.status}`;
	} catch {
		return `HTTP ${response.status}`;
	}
};

const normalizeSuggestion = (
	suggestion: ApiScheduleSuggestion | undefined,
): CreateScheduleSuggestion | null => {
	if (!suggestion) return null;
	const suggestedStart = suggestion.suggested_start ?? suggestion.suggestedStart;
	const suggestedEnd = suggestion.suggested_end ?? suggestion.suggestedEnd;
	if (!suggestedStart || !suggestedEnd) return null;
	return {
		suggestedStart,
		suggestedEnd,
		reason: suggestion.reason ?? "",
		alternatives: (suggestion.alternatives ?? [])
			.map((alternative) => {
				const alternativeStart =
					alternative.suggested_start ?? alternative.suggestedStart;
				const alternativeEnd =
					alternative.suggested_end ?? alternative.suggestedEnd;
				if (!alternativeStart || !alternativeEnd) return null;
				return {
					suggestedStart: alternativeStart,
					suggestedEnd: alternativeEnd,
				};
			})
			.filter((item): item is ScheduleHintOption => item !== null),
	};
};

export const requestCreateScheduleSuggestion = async ({
	title,
	priority = "none",
	due = null,
	duration = DEFAULT_CREATE_DURATION,
	planningStart = null,
	planningEnd = null,
	blockedSlots,
}: CreateScheduleSuggestionInput): Promise<CreateScheduleSuggestion | null> => {
	const startDate = toDate(planningStart) ?? new Date();
	const endDate =
		toDate(planningEnd) ?? addDays(startDate, DEFAULT_PLANNING_WINDOW_DAYS);
	const response = await fetch("/api/agent/schedule-suggest", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			todos: [
				{
					id: 1,
					name: title.trim() || "新待办",
					priority,
					due,
					duration: duration || DEFAULT_CREATE_DURATION,
				},
			],
			schedule_constraints: [],
			blocked_slots: blockedSlots,
			planning_start: startDate.toISOString(),
			planning_end: endDate.toISOString(),
			daily_available_hours: 6,
		}),
	});

	if (!response.ok) {
		throw new Error(await parseApiError(response));
	}

	const data = (await response.json()) as ApiScheduleSuggestResponse;
	return normalizeSuggestion(data.suggestions?.[0]);
};

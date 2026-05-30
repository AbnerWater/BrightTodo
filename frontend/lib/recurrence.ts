export type RecurrencePreset =
	| "none"
	| "daily"
	| "weekly"
	| "monthly"
	| "yearly"
	| "custom";

export type RecurrenceCustomFrequency = "weekly" | "monthly" | "yearly";

export interface RecurrenceDraft {
	preset: RecurrencePreset;
	customFrequency: RecurrenceCustomFrequency;
	weekdays: string[];
	monthDays: number[];
	months: number[];
	yearMonthDays: number[];
}

export const WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];

export const MONTH_NUMBERS = Array.from({ length: 12 }, (_, index) => index + 1);
export const MONTH_DAY_NUMBERS = Array.from(
	{ length: 31 },
	(_, index) => index + 1,
);

const DEFAULT_DRAFT: RecurrenceDraft = {
	preset: "none",
	customFrequency: "weekly",
	weekdays: ["MO"],
	monthDays: [1],
	months: [1],
	yearMonthDays: [1],
};

const PRESET_TO_RULE: Record<Exclude<RecurrencePreset, "none" | "custom">, string> =
	{
		daily: "FREQ=DAILY",
		weekly: "FREQ=WEEKLY",
		monthly: "FREQ=MONTHLY",
		yearly: "FREQ=YEARLY",
	};

function uniqueSortedNumbers(values: number[]): number[] {
	return Array.from(new Set(values))
		.filter((value) => Number.isInteger(value) && value > 0)
		.sort((a, b) => a - b);
}

function uniqueWeekdays(values: string[]): string[] {
	const selected = new Set(values);
	return WEEKDAY_CODES.filter((code) => selected.has(code));
}

function parseParts(rrule?: string | null): Record<string, string> {
	if (!rrule) return {};
	return rrule.split(";").reduce<Record<string, string>>((acc, part) => {
		const [rawKey, ...rawValue] = part.split("=");
		const key = rawKey?.trim().toUpperCase();
		const value = rawValue.join("=").trim();
		if (key && value) {
			acc[key] = value;
		}
		return acc;
	}, {});
}

function parseNumberList(value?: string): number[] {
	if (!value) return [];
	return uniqueSortedNumbers(
		value
			.split(",")
			.map((item) => Number.parseInt(item.trim(), 10))
			.filter((item) => !Number.isNaN(item)),
	);
}

export function parseRecurrenceRule(rrule?: string | null): RecurrenceDraft {
	const parts = parseParts(rrule);
	const freq = parts.FREQ?.toUpperCase();
	const weekdays = uniqueWeekdays((parts.BYDAY ?? "").split(","));
	const monthDays = parseNumberList(parts.BYMONTHDAY).filter(
		(day) => day >= 1 && day <= 31,
	);
	const months = parseNumberList(parts.BYMONTH).filter(
		(month) => month >= 1 && month <= 12,
	);

	if (!freq) return { ...DEFAULT_DRAFT };

	if (freq === "DAILY" && !parts.BYDAY && !parts.BYMONTHDAY && !parts.BYMONTH) {
		return { ...DEFAULT_DRAFT, preset: "daily" };
	}
	if (freq === "WEEKLY" && !parts.BYDAY) {
		return { ...DEFAULT_DRAFT, preset: "weekly" };
	}
	if (freq === "MONTHLY" && !parts.BYMONTHDAY) {
		return { ...DEFAULT_DRAFT, preset: "monthly" };
	}
	if (freq === "YEARLY" && !parts.BYMONTH && !parts.BYMONTHDAY) {
		return { ...DEFAULT_DRAFT, preset: "yearly" };
	}

	if (freq === "MONTHLY") {
		return {
			...DEFAULT_DRAFT,
			preset: "custom",
			customFrequency: "monthly",
			monthDays: monthDays.length ? monthDays : DEFAULT_DRAFT.monthDays,
		};
	}

	if (freq === "YEARLY") {
		return {
			...DEFAULT_DRAFT,
			preset: "custom",
			customFrequency: "yearly",
			months: months.length ? months : DEFAULT_DRAFT.months,
			yearMonthDays: monthDays.length
				? monthDays
				: DEFAULT_DRAFT.yearMonthDays,
		};
	}

	return {
		...DEFAULT_DRAFT,
		preset: "custom",
		customFrequency: "weekly",
		weekdays: weekdays.length ? weekdays : DEFAULT_DRAFT.weekdays,
	};
}

export function buildRecurrenceRule(draft: RecurrenceDraft): string | null {
	if (draft.preset === "none") return null;
	if (draft.preset !== "custom") return PRESET_TO_RULE[draft.preset];

	if (draft.customFrequency === "weekly") {
		const weekdays = uniqueWeekdays(draft.weekdays);
		return weekdays.length
			? `FREQ=WEEKLY;BYDAY=${weekdays.join(",")}`
			: "FREQ=WEEKLY";
	}

	if (draft.customFrequency === "monthly") {
		const monthDays = uniqueSortedNumbers(draft.monthDays).filter(
			(day) => day >= 1 && day <= 31,
		);
		return monthDays.length
			? `FREQ=MONTHLY;BYMONTHDAY=${monthDays.join(",")}`
			: "FREQ=MONTHLY";
	}

	const months = uniqueSortedNumbers(draft.months).filter(
		(month) => month >= 1 && month <= 12,
	);
	const monthDays = uniqueSortedNumbers(draft.yearMonthDays).filter(
		(day) => day >= 1 && day <= 31,
	);
	const segments = ["FREQ=YEARLY"];
	if (months.length) segments.push(`BYMONTH=${months.join(",")}`);
	if (monthDays.length) segments.push(`BYMONTHDAY=${monthDays.join(",")}`);
	return segments.join(";");
}

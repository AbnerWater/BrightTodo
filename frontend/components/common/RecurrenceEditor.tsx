"use client";

import { Repeat } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useMemo } from "react";
import {
	buildRecurrenceRule,
	MONTH_DAY_NUMBERS,
	MONTH_NUMBERS,
	parseRecurrenceRule,
	type RecurrenceCustomFrequency,
	type RecurrenceDraft,
	type RecurrencePreset,
	WEEKDAY_CODES,
} from "@/lib/recurrence";
import { cn } from "@/lib/utils";

interface RecurrenceEditorProps {
	value?: string | null;
	onChange: (value: string | null) => void;
	className?: string;
	compact?: boolean;
	disabled?: boolean;
}

const presetOptions: RecurrencePreset[] = [
	"none",
	"daily",
	"weekly",
	"monthly",
	"yearly",
	"custom",
];

const customFrequencyOptions: RecurrenceCustomFrequency[] = [
	"weekly",
	"monthly",
	"yearly",
];

const presetLabelKeys: Record<RecurrencePreset, string> = {
	none: "repeatNone",
	daily: "repeatDaily",
	weekly: "repeatWeekly",
	monthly: "repeatMonthly",
	yearly: "repeatYearly",
	custom: "repeatCustom",
};

const customFrequencyLabelKeys: Record<RecurrenceCustomFrequency, string> = {
	weekly: "repeatWeeklyCustom",
	monthly: "repeatMonthlyCustom",
	yearly: "repeatYearlyCustom",
};

function toggleString(values: string[], value: string): string[] {
	return values.includes(value)
		? values.filter((item) => item !== value)
		: [...values, value];
}

function toggleNumber(values: number[], value: number): number[] {
	return values.includes(value)
		? values.filter((item) => item !== value)
		: [...values, value];
}

function toggleStringRequired(values: string[], value: string): string[] {
	if (values.includes(value) && values.length <= 1) return values;
	return toggleString(values, value);
}

function toggleNumberRequired(values: number[], value: number): number[] {
	if (values.includes(value) && values.length <= 1) return values;
	return toggleNumber(values, value);
}

function withCustomDefaults(
	draft: RecurrenceDraft,
	customFrequency: RecurrenceCustomFrequency,
): RecurrenceDraft {
	if (customFrequency === "weekly") {
		return {
			...draft,
			preset: "custom",
			customFrequency,
			weekdays: draft.weekdays.length ? draft.weekdays : ["MO"],
		};
	}
	if (customFrequency === "monthly") {
		return {
			...draft,
			preset: "custom",
			customFrequency,
			monthDays: draft.monthDays.length ? draft.monthDays : [1],
		};
	}
	return {
		...draft,
		preset: "custom",
		customFrequency,
		months: draft.months.length ? draft.months : [1],
		yearMonthDays: draft.yearMonthDays.length ? draft.yearMonthDays : [1],
	};
}

export function formatRecurrenceLabel(
	value: string | null | undefined,
	t: ReturnType<typeof useTranslations<"datePicker">>,
): string {
	const draft = parseRecurrenceRule(value);
	if (draft.preset !== "custom") {
		return t(presetLabelKeys[draft.preset]);
	}
	if (draft.customFrequency === "weekly") {
		const separator = t("listSeparator");
		const days = draft.weekdays
			.map((day) => t(`weekdayShort.${day}`))
			.join(separator);
		return days ? t("repeatCustomWeeklySummary", { days }) : t("repeatWeekly");
	}
	if (draft.customFrequency === "monthly") {
		const separator = t("listSeparator");
		const days = draft.monthDays
			.map((day) => t("dayOption", { day }))
			.join(separator);
		return days ? t("repeatCustomMonthlySummary", { days }) : t("repeatMonthly");
	}
	const separator = t("listSeparator");
	const months = draft.months
		.map((month) => t("monthOption", { month }))
		.join(separator);
	const days = draft.yearMonthDays
		.map((day) => t("dayOption", { day }))
		.join(separator);
	if (months && days) {
		return t("repeatCustomYearlySummary", { months, days });
	}
	return t("repeatYearly");
}

export function RecurrenceEditor({
	value,
	onChange,
	className,
	compact = false,
	disabled = false,
}: RecurrenceEditorProps) {
	const t = useTranslations("datePicker");
	const selectId = useId();
	const customFrequencyId = useId();
	const draft = useMemo(() => parseRecurrenceRule(value), [value]);

	const emit = (next: RecurrenceDraft) => {
		onChange(buildRecurrenceRule(next));
	};

	const handlePresetChange = (preset: RecurrencePreset) => {
		if (preset === "custom") {
			emit(withCustomDefaults(draft, draft.customFrequency));
			return;
		}
		emit({ ...draft, preset });
	};

	const handleCustomFrequencyChange = (
		customFrequency: RecurrenceCustomFrequency,
	) => {
		emit(withCustomDefaults(draft, customFrequency));
	};

	const renderChip = ({
		key,
		label,
		selected,
		onClick,
	}: {
		key: string;
		label: string;
		selected: boolean;
		onClick: () => void;
	}) => (
		<button
			key={key}
			type="button"
			disabled={disabled}
			onClick={onClick}
			aria-pressed={selected}
			className={cn(
				"min-h-8 rounded-md border px-2 text-xs font-medium transition-colors",
				selected
					? "border-primary/70 bg-primary/10 text-primary"
					: "border-border/70 text-muted-foreground hover:bg-muted/60 hover:text-foreground",
				disabled && "cursor-not-allowed opacity-60",
			)}
		>
			{label}
		</button>
	);

	return (
		<div className={cn("space-y-2", className)}>
			<label
				htmlFor={selectId}
				className="flex items-center gap-2 text-xs font-medium text-muted-foreground"
			>
				<Repeat className="h-3.5 w-3.5" />
				{t("repeatLabel")}
			</label>
			<select
				id={selectId}
				value={draft.preset}
				disabled={disabled}
				onChange={(event) =>
					handlePresetChange(event.target.value as RecurrencePreset)
				}
				className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
			>
				{presetOptions.map((preset) => (
					<option key={preset} value={preset}>
						{t(presetLabelKeys[preset])}
					</option>
				))}
			</select>

			{draft.preset === "custom" && (
				<div className="space-y-3 rounded-lg border border-border/70 bg-muted/20 p-3">
					<div className="space-y-1.5">
						<label
							htmlFor={customFrequencyId}
							className="text-[11px] font-medium text-muted-foreground"
						>
							{t("repeatCustomUnit")}
						</label>
						<select
							id={customFrequencyId}
							value={draft.customFrequency}
							disabled={disabled}
							onChange={(event) =>
								handleCustomFrequencyChange(
									event.target.value as RecurrenceCustomFrequency,
								)
							}
							className="w-full rounded-md border border-border/70 bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
						>
							{customFrequencyOptions.map((option) => (
								<option key={option} value={option}>
									{t(customFrequencyLabelKeys[option])}
								</option>
							))}
						</select>
					</div>

					{draft.customFrequency === "weekly" && (
						<div className="space-y-1.5">
							<div className="text-[11px] font-medium text-muted-foreground">
								{t("repeatWeekdays")}
							</div>
							<div className="grid grid-cols-7 gap-1">
								{WEEKDAY_CODES.map((weekday) =>
									renderChip({
										key: weekday,
										label: t(`weekdayShort.${weekday}`),
										selected: draft.weekdays.includes(weekday),
										onClick: () =>
											emit({
												...draft,
												weekdays: toggleStringRequired(
													draft.weekdays,
													weekday,
												),
											}),
									}),
								)}
							</div>
						</div>
					)}

					{draft.customFrequency === "monthly" && (
						<div className="space-y-1.5">
							<div className="text-[11px] font-medium text-muted-foreground">
								{t("repeatMonthDays")}
							</div>
							<div
								className={cn(
									"grid grid-cols-7 gap-1 overflow-y-auto pr-1",
									compact ? "max-h-28" : "max-h-36",
								)}
							>
								{MONTH_DAY_NUMBERS.map((day) =>
									renderChip({
										key: String(day),
										label: String(day),
										selected: draft.monthDays.includes(day),
										onClick: () =>
											emit({
												...draft,
												monthDays: toggleNumberRequired(
													draft.monthDays,
													day,
												),
											}),
									}),
								)}
							</div>
						</div>
					)}

					{draft.customFrequency === "yearly" && (
						<div className="space-y-3">
							<div className="space-y-1.5">
								<div className="text-[11px] font-medium text-muted-foreground">
									{t("repeatMonths")}
								</div>
								<div className="grid grid-cols-4 gap-1">
									{MONTH_NUMBERS.map((month) =>
										renderChip({
											key: String(month),
											label: t("monthShort", { month }),
											selected: draft.months.includes(month),
											onClick: () =>
												emit({
													...draft,
													months: toggleNumberRequired(
														draft.months,
														month,
													),
												}),
										}),
									)}
								</div>
							</div>
							<div className="space-y-1.5">
								<div className="text-[11px] font-medium text-muted-foreground">
									{t("repeatYearDays")}
								</div>
								<div
									className={cn(
										"grid grid-cols-7 gap-1 overflow-y-auto pr-1",
										compact ? "max-h-28" : "max-h-36",
									)}
								>
									{MONTH_DAY_NUMBERS.map((day) =>
										renderChip({
											key: String(day),
											label: String(day),
											selected: draft.yearMonthDays.includes(day),
											onClick: () =>
												emit({
													...draft,
													yearMonthDays: toggleNumberRequired(
														draft.yearMonthDays,
														day,
													),
												}),
										}),
									)}
								</div>
							</div>
						</div>
					)}

					<p className="text-[11px] leading-4 text-muted-foreground">
						{t("repeatCustomHint")}
					</p>
				</div>
			)}
		</div>
	);
}

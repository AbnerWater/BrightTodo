"use client";

import { AlertTriangle, CheckCircle2, Clock, Loader2, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import type React from "react";
import { useEffect, useRef } from "react";
import { RecurrenceEditor } from "@/components/common/RecurrenceEditor";
import type {
	CreateScheduleSuggestion,
	ScheduleHintConflict,
	ScheduleHintOption,
} from "@/lib/scheduleHints";
import { formatScheduleRange } from "@/lib/scheduleHints";
import { cn } from "@/lib/utils";

interface NewTodoInlineFormProps {
	value: string;
	onChange: (value: string) => void;
	rrule?: string | null;
	onRruleChange?: (value: string | null) => void;
	startTime: string;
	endTime: string;
	onStartTimeChange: (value: string) => void;
	onEndTimeChange: (value: string) => void;
	conflicts: ScheduleHintConflict[];
	suggestion: CreateScheduleSuggestion | null;
	isSuggesting: boolean;
	suggestionError: string | null;
	onSuggestSchedule: () => void;
	onUseSuggestion: (option: ScheduleHintOption) => void;
	onSubmit: (e?: React.FormEvent) => void;
	onCancel: () => void;
}

export function NewTodoInlineForm({
	value,
	onChange,
	rrule,
	onRruleChange,
	startTime,
	endTime,
	onStartTimeChange,
	onEndTimeChange,
	conflicts,
	suggestion,
	isSuggesting,
	suggestionError,
	onSuggestSchedule,
	onUseSuggestion,
	onSubmit,
	onCancel,
}: NewTodoInlineFormProps) {
	const t = useTranslations("todoList");
	const inputRef = useRef<HTMLInputElement>(null);
	const hasScheduleInput = Boolean(startTime && endTime);
	const conflictLabel = conflicts
		.map((conflict) =>
			conflict.label || formatScheduleRange(conflict.start, conflict.end),
		)
		.join("、");

	useEffect(() => {
		inputRef.current?.focus();
	}, []);

	useEffect(() => {
		if (value === "") {
			inputRef.current?.focus();
		}
	}, [value]);

	return (
		<form
			onSubmit={onSubmit}
			onReset={onCancel}
			className="group rounded-lg border border-border/60 bg-muted/30 px-3 py-2 transition-colors focus-within:border-primary focus-within:bg-background focus-within:ring-2 focus-within:ring-primary/40"
			onClick={(event) => {
				if (
					event.target instanceof HTMLElement &&
					event.target.closest("[data-recurrence-editor], [data-schedule-hints]")
				) {
					return;
				}
				inputRef.current?.focus();
			}}
			onKeyDown={(e) => {
				// 仅在表单容器聚焦时处理键盘操作，避免阻断输入框的 Enter 提交
				if (e.currentTarget !== e.target) return;
				if (e.key === " ") {
					e.preventDefault();
					inputRef.current?.focus();
					return;
				}
				if (e.key === "Enter") {
					inputRef.current?.focus();
				}
			}}
		>
			<div className="flex items-center gap-3">
				<Plus className="h-4 w-4 text-muted-foreground group-focus-within:text-primary" />
				<input
					ref={inputRef}
					type="text"
					value={value}
					onChange={(e) => onChange(e.target.value)}
					placeholder={t("addTodo")}
					className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
					required
				/>
			</div>
			{value.trim() && onRruleChange && (
				<div className="mt-3 border-t border-border/60 pt-3" data-recurrence-editor>
					<RecurrenceEditor value={rrule} onChange={onRruleChange} compact />
				</div>
			)}
			{value.trim() && (
				<div
					className="mt-3 border-t border-border/60 pt-3"
					data-schedule-hints
				>
					<div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
						<label className="min-w-0 text-xs text-muted-foreground">
							<span className="mb-1 block">{t("scheduleStartLabel")}</span>
							<input
								type="datetime-local"
								value={startTime}
								onChange={(event) => onStartTimeChange(event.target.value)}
								className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
							/>
						</label>
						<label className="min-w-0 text-xs text-muted-foreground">
							<span className="mb-1 block">{t("scheduleEndLabel")}</span>
							<input
								type="datetime-local"
								value={endTime}
								onChange={(event) => onEndTimeChange(event.target.value)}
								className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
							/>
						</label>
						<button
							type="button"
							onClick={onSuggestSchedule}
							disabled={isSuggesting}
							className="mt-5 inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
						>
							{isSuggesting ? (
								<Loader2 className="h-3.5 w-3.5 animate-spin" />
							) : (
								<Clock className="h-3.5 w-3.5" />
							)}
							{isSuggesting ? t("recommendingFreeTime") : t("recommendFreeTime")}
						</button>
					</div>

					<div className="mt-2 space-y-2">
						{hasScheduleInput && conflicts.length > 0 && (
							<div className="rounded-md border border-amber-300/70 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
								<div className="flex items-center gap-1.5 font-medium">
									<AlertTriangle className="h-3.5 w-3.5" />
									{t("scheduleConflictTitle")}
								</div>
								<p className="mt-1">
									{t("scheduleConflictWith", { label: conflictLabel })}
								</p>
								<p className="mt-1 text-amber-700 dark:text-amber-200/80">
									{t("scheduleConflictNonBlocking")}
								</p>
							</div>
						)}
						{hasScheduleInput && conflicts.length === 0 && (
							<div className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300">
								<CheckCircle2 className="h-3.5 w-3.5" />
								{t("scheduleNoConflict")}
							</div>
						)}
						{suggestionError && (
							<p className="text-xs text-destructive">
								{t("recommendationFailed", { error: suggestionError })}
							</p>
						)}
						{suggestion && (
							<div className="rounded-md border border-border bg-background/70 px-3 py-2 text-xs">
								<div className="flex flex-wrap items-center gap-2">
									<span className="font-medium text-foreground">
										{t("recommendedSlot", {
											time: formatScheduleRange(
												suggestion.suggestedStart,
												suggestion.suggestedEnd,
											),
										})}
									</span>
									<button
										type="button"
										onClick={() => onUseSuggestion(suggestion)}
										className="rounded-md border border-border px-2 py-1 text-foreground hover:bg-muted"
									>
										{t("useRecommendedSlot", {
											time: formatScheduleRange(
												suggestion.suggestedStart,
												suggestion.suggestedEnd,
											),
										})}
									</button>
								</div>
								{suggestion.alternatives.length > 0 && (
									<div className="mt-2 flex flex-wrap items-center gap-1.5">
										<span className="text-muted-foreground">
											{t("alternativeSlots")}
										</span>
										{suggestion.alternatives.map((alternative) => (
											<button
												key={`${alternative.suggestedStart}-${alternative.suggestedEnd}`}
												type="button"
												onClick={() => onUseSuggestion(alternative)}
												className="rounded-md border border-border px-2 py-1 text-foreground hover:bg-muted"
											>
												{formatScheduleRange(
													alternative.suggestedStart,
													alternative.suggestedEnd,
												)}
											</button>
										))}
									</div>
								)}
							</div>
						)}
					</div>
				</div>
			)}
			<div className="mt-3 flex justify-end" data-schedule-hints>
				<button
					type="submit"
					className={cn(
						"inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-sm transition hover:bg-primary/90",
						!value.trim() && "hidden",
					)}
				>
					<Plus className="h-3.5 w-3.5" />
					{conflicts.length > 0 ? t("createAnyway") : t("add")}
				</button>
			</div>
			<button type="reset" className="sr-only">
				{t("reset")}
			</button>
		</form>
	);
}

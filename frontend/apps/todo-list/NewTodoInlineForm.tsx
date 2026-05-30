"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import type React from "react";
import { useEffect, useRef } from "react";
import { RecurrenceEditor } from "@/components/common/RecurrenceEditor";

interface NewTodoInlineFormProps {
	value: string;
	onChange: (value: string) => void;
	rrule?: string | null;
	onRruleChange?: (value: string | null) => void;
	onSubmit: (e?: React.FormEvent) => void;
	onCancel: () => void;
}

export function NewTodoInlineForm({
	value,
	onChange,
	rrule,
	onRruleChange,
	onSubmit,
	onCancel,
}: NewTodoInlineFormProps) {
	const t = useTranslations("todoList");
	const inputRef = useRef<HTMLInputElement>(null);

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
					event.target.closest("[data-recurrence-editor]")
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
			<button type="submit" className="sr-only">
				{t("submit")}
			</button>
			<button type="reset" className="sr-only">
				{t("reset")}
			</button>
		</form>
	);
}

"use client";

import { AlertTriangle, Check, Clock, Loader2, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import type {
	Todo,
	TodoTimeOptimizationItem,
	TodoTimeOptimizationResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { formatScheduleLabel } from "./utils/todoCardUtils";

interface TodoTimeOptimizationPreviewDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	todo: Todo | null;
	result: TodoTimeOptimizationResponse | null;
	isLoading: boolean;
	error: string | null;
	isConfirming: boolean;
	onConfirm: () => void;
}

function formatTimeRange(
	range: { startTime?: string | null; endTime?: string | null } | null,
	emptyText: string,
) {
	if (!range) return emptyText;
	return (
		formatScheduleLabel(range.startTime ?? undefined, range.endTime ?? undefined) ??
		emptyText
	);
}

function getOptimizationItems(
	result: TodoTimeOptimizationResponse | null,
): TodoTimeOptimizationItem[] {
	if (!result) return [];
	if (result.items?.length > 0) return result.items;
	return [
		{
			todoId: result.todoId,
			todoName: result.todoName,
			parentTodoId: null,
			status: "active",
			depth: 0,
			before: result.before,
			after: result.after,
			hasConflict: result.hasConflict,
			conflicts: result.conflicts,
			reason: result.reason,
			confidence: result.confidence,
		},
	];
}

export function TodoTimeOptimizationPreviewDialog({
	open,
	onOpenChange,
	todo,
	result,
	isLoading,
	error,
	isConfirming,
	onConfirm,
}: TodoTimeOptimizationPreviewDialogProps) {
	const t = useTranslations("todoList");
	const optimizationItems = getOptimizationItems(result);
	const canConfirm =
		optimizationItems.length > 0 &&
		optimizationItems.every((item) => item.after.startTime && item.after.endTime) &&
		!isLoading &&
		!error &&
		!isConfirming;
	const statusLabels = {
		active: t("statusActive"),
		completed: t("statusCompleted"),
		canceled: t("statusCanceled"),
		draft: t("statusDraft"),
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-h-[86vh] max-w-2xl overflow-hidden p-0">
				<DialogHeader className="border-b border-border px-4 py-3">
					<div className="flex items-center gap-2">
						<Sparkles className="h-5 w-5 shrink-0 text-primary" />
						<DialogTitle>{t("timeOptimizationTitle")}</DialogTitle>
					</div>
					<DialogDescription>
						{todo?.name ?? t("timeOptimizationUnknownTodo")}
					</DialogDescription>
				</DialogHeader>

				<div className="max-h-[60vh] overflow-y-auto px-4 py-4">
					{isLoading && (
						<div className="flex min-h-40 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
							<Loader2 className="h-6 w-6 animate-spin text-primary" />
							<span>{t("timeOptimizationLoading")}</span>
						</div>
					)}

					{!isLoading && error && (
						<div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
							<div className="flex items-center gap-2 font-medium">
								<AlertTriangle className="h-4 w-4" />
								{t("timeOptimizationErrorTitle")}
							</div>
							<p className="mt-2 text-sm">{error}</p>
						</div>
					)}

					{!isLoading && !error && result && (
						<div className="space-y-4">
							<div
								className={cn(
									"inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium",
									result.hasConflict
										? "border-amber-300/70 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
										: "border-emerald-300/70 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200",
								)}
							>
									<Clock className="h-3.5 w-3.5" />
								{result.hasConflict
									? t("timeOptimizationConflict", {
											count: result.conflicts.length,
										})
									: t("timeOptimizationNoConflict")}
							</div>

							<div className="text-sm text-muted-foreground">
								{t("timeOptimizationAffectedCount", {
									count: optimizationItems.length,
								})}
							</div>

							<div className="space-y-3">
								{optimizationItems.map((item) => (
									<div
										key={item.todoId}
										className="rounded-md border border-border p-3"
									>
										<div className="flex min-w-0 items-center justify-between gap-3">
											<div
												className="min-w-0"
												style={{ marginLeft: item.depth * 12 }}
											>
												<div className="truncate text-sm font-medium text-foreground">
													{item.todoName}
												</div>
												<div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
													<span>{statusLabels[item.status]}</span>
													{item.depth > 0 && (
														<span>
															{t("timeOptimizationChildDepth", {
																depth: item.depth,
															})}
														</span>
													)}
												</div>
											</div>
											<span
												className={cn(
													"shrink-0 rounded-sm px-2 py-0.5 text-xs font-medium",
													item.hasConflict
														? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200"
														: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200",
												)}
											>
												{item.hasConflict
													? t("timeOptimizationItemConflict", {
															count: item.conflicts.length,
														})
													: t("timeOptimizationItemNoConflict")}
											</span>
										</div>

										<div className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-2">
											<div>
												<div className="text-xs font-medium text-muted-foreground">
													{t("timeOptimizationBefore")}
												</div>
												<div className="mt-1 text-sm text-foreground">
													{formatTimeRange(
														item.before,
														t("timeOptimizationNotScheduled"),
													)}
												</div>
											</div>
											<div>
												<div className="text-xs font-medium text-muted-foreground">
													{t("timeOptimizationAfter")}
												</div>
												<div className="mt-1 text-sm font-medium text-foreground">
													{formatTimeRange(
														item.after,
														t("timeOptimizationNotScheduled"),
													)}
												</div>
											</div>
										</div>

										{item.conflicts.length > 0 && (
											<div className="mt-3 border-t border-border pt-3">
												<div className="text-xs font-medium text-muted-foreground">
													{t("timeOptimizationConflictList")}
												</div>
												<div className="mt-2 space-y-1.5">
													{item.conflicts.map((conflict) => (
														<div
															key={conflict.id}
															className="flex items-center justify-between gap-3 text-sm"
														>
															<span className="min-w-0 truncate text-foreground">
																{conflict.name}
															</span>
															<span className="shrink-0 text-xs text-muted-foreground">
																{formatScheduleLabel(
																	conflict.startTime,
																	conflict.endTime,
																)}
															</span>
														</div>
													))}
												</div>
											</div>
										)}

										<div className="mt-3 border-t border-border pt-3">
											<div className="text-xs font-medium text-muted-foreground">
												{t("timeOptimizationReason")}
											</div>
											<p className="mt-1 text-sm leading-6 text-foreground">
												{item.reason}
											</p>
											<div className="mt-2 text-xs text-muted-foreground">
												{t("timeOptimizationConfidence", {
													value: Math.round(item.confidence * 100),
												})}
											</div>
										</div>
									</div>
								))}
							</div>
						</div>
					)}
				</div>

				<DialogFooter className="border-t border-border px-4 py-3">
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={isConfirming}
					>
						{t("timeOptimizationCancel")}
					</Button>
					<Button type="button" onClick={onConfirm} disabled={!canConfirm}>
						{isConfirming ? (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						) : (
							<Check className="mr-2 h-4 w-4" />
						)}
						{t("timeOptimizationConfirm")}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

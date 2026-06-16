import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
	formatScheduleLabel,
	getPriorityBorderColor,
} from "../apps/todo-list/utils/todoCardUtils.ts";

describe("Todo 卡片工具", () => {
	it("没有有效时间时不展示日程标签", () => {
		assert.equal(formatScheduleLabel(), null);
		assert.equal(formatScheduleLabel("invalid-date"), null);
	});

	it("开始时间缺失时使用结束时间", () => {
		const endTime = "2026-06-02T09:30:00";

		assert.equal(formatScheduleLabel(undefined, endTime), formatScheduleLabel(endTime));
	});

	it("午夜时间只展示日期", () => {
		const result = formatScheduleLabel("2026-06-02T00:00:00");

		assert.equal(result, "Jun 2, 2026");
	});

	it("将优先级映射到对应边框样式", () => {
		assert.equal(getPriorityBorderColor("high"), "border-destructive/60");
		assert.equal(getPriorityBorderColor("medium"), "border-primary/60");
		assert.equal(getPriorityBorderColor("low"), "border-secondary/60");
		assert.equal(getPriorityBorderColor("none"), "border-muted-foreground/40");
	});
});

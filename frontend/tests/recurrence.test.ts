import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
	buildRecurrenceRule,
	parseRecurrenceRule,
	type RecurrenceDraft,
} from "../lib/recurrence.ts";

const createDraft = (
	overrides: Partial<RecurrenceDraft> = {},
): RecurrenceDraft => ({
	preset: "none",
	customFrequency: "weekly",
	weekdays: ["MO"],
	monthDays: [1],
	months: [1],
	yearMonthDays: [1],
	...overrides,
});

describe("重复规则", () => {
	it("将空规则解析为不重复", () => {
		assert.deepEqual(parseRecurrenceRule(null), createDraft());
	});

	it("识别内置重复周期", () => {
		assert.equal(parseRecurrenceRule("FREQ=DAILY").preset, "daily");
		assert.equal(parseRecurrenceRule("FREQ=WEEKLY").preset, "weekly");
		assert.equal(parseRecurrenceRule("FREQ=MONTHLY").preset, "monthly");
		assert.equal(parseRecurrenceRule("FREQ=YEARLY").preset, "yearly");
	});

	it("解析自定义每周规则并按标准顺序去重", () => {
		const result = parseRecurrenceRule("FREQ=WEEKLY;BYDAY=FR,MO,FR");

		assert.equal(result.preset, "custom");
		assert.equal(result.customFrequency, "weekly");
		assert.deepEqual(result.weekdays, ["MO", "FR"]);
	});

	it("生成自定义每月规则时过滤越界日期并去重", () => {
		const result = buildRecurrenceRule(
			createDraft({
				preset: "custom",
				customFrequency: "monthly",
				monthDays: [31, 2, 2, 0, 32],
			}),
		);

		assert.equal(result, "FREQ=MONTHLY;BYMONTHDAY=2,31");
	});

	it("生成自定义每年规则时过滤越界月份", () => {
		const result = buildRecurrenceRule(
			createDraft({
				preset: "custom",
				customFrequency: "yearly",
				months: [12, 1, 13],
				yearMonthDays: [15],
			}),
		);

		assert.equal(result, "FREQ=YEARLY;BYMONTH=1,12;BYMONTHDAY=15");
	});
});

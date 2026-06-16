import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
	localToUtcIso,
	utcToLocalDisplay,
	utcToLocalInput,
} from "../lib/utils/time.ts";

describe("时间转换工具", () => {
	it("为空值和非法日期返回空字符串", () => {
		assert.equal(utcToLocalInput(""), "");
		assert.equal(utcToLocalInput("invalid-date"), "");
		assert.equal(localToUtcIso(""), "");
		assert.equal(localToUtcIso("invalid-date"), "");
		assert.equal(utcToLocalDisplay("invalid-date"), "");
	});

	it("可以在本地输入格式和 UTC ISO 格式之间往返转换", () => {
		const localInput = "2026-06-02T09:30";

		assert.equal(utcToLocalInput(localToUtcIso(localInput)), localInput);
	});

	it("根据展示模式调用对应的本地化格式", () => {
		const iso = "2026-06-02T09:30:00.000Z";
		const date = new Date(iso);

		assert.equal(utcToLocalDisplay(iso, "date"), date.toLocaleDateString());
		assert.equal(utcToLocalDisplay(iso, "time"), date.toLocaleTimeString());
		assert.equal(utcToLocalDisplay(iso), date.toLocaleString());
	});
});

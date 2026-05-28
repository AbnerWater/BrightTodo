"use client";

import { useTranslations } from "next-intl";

/**
 * 版本信息组件
 * 显示当前应用版本号、构建类型和 Git Commit
 */
export function VersionInfoSection() {
	const t = useTranslations("page.settings");

	const version = process.env.NEXT_PUBLIC_APP_VERSION || "unknown";
	const gitCommit = process.env.NEXT_PUBLIC_GIT_COMMIT || "unknown";
	const buildType = process.env.NEXT_PUBLIC_BUILD_TYPE || "unknown";

	// 格式：版本号_版本类型_Git Commit
	const versionString = `${version}_${buildType}_${gitCommit}`;

	return (
		<div className="space-y-3 text-sm text-muted-foreground">
			<div className="text-center">
				<span>{t("currentVersion")}：</span>
				<span className="font-mono">{versionString}</span>
			</div>
			<div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-left">
				<div className="font-medium text-foreground">{t("sourceProject")}</div>
				<p className="mt-1 leading-relaxed">{t("sourceProjectDescription")}</p>
			</div>
		</div>
	);
}

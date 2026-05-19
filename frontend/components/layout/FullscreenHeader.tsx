/**
 * Maximize 模式 Header 组件
 */

"use client";

import Image from "next/image";
import { LayoutSelector } from "@/components/common/layout/LayoutSelector";
import { ThemeStyleSelect } from "@/components/common/theme/ThemeStyleSelect";
import { ThemeToggle } from "@/components/common/theme/ThemeToggle";
import { LanguageToggle } from "@/components/common/ui/LanguageToggle";
import { SettingsToggle } from "@/components/common/ui/SettingsToggle";
import { HeaderIsland } from "@/components/notification/HeaderIsland";

interface MaximizeHeaderProps {
	hasNotifications: boolean;
}

export function MaximizeHeader({ hasNotifications }: MaximizeHeaderProps) {
	return (
		<header className="relative flex h-15 shrink-0 items-center bg-primary-foreground dark:bg-accent px-4 text-foreground overflow-visible">
			{/* 左侧：Logo */}
			<div className="flex items-center gap-2 shrink-0">
				<div className="relative h-8 w-8 shrink-0">
					{/* 浅色模式图标 */}
					<Image
						src="/free-todo-logos/free_todo_icon_4_dark_with_grid.png"
						alt="Free Todo Logo"
						width={32}
						height={32}
						className="object-contain block dark:hidden"
					/>
					{/* 深色模式图标 */}
					<Image
						src="/free-todo-logos/free_todo_icon_4_with_grid.png"
						alt="Free Todo Logo"
						width={32}
						height={32}
						className="object-contain hidden dark:block"
					/>
				</div>
				<h1 className="text-lg font-semibold tracking-tight text-foreground">
					Free Todo: Your AI Secretary
				</h1>
			</div>

			{/* 中间：通知区域 */}
			{hasNotifications && (
				<div className="flex-1 flex items-center justify-center relative min-w-0 overflow-visible">
					<HeaderIsland />
				</div>
			)}

			{/* 占位符：当没有通知时保持布局平衡 */}
			{!hasNotifications && <div className="flex-1" />}

			{/* 右侧：工具 */}
			<div className="flex items-center gap-2 shrink-0">
				<LayoutSelector />
				<ThemeStyleSelect />
				<ThemeToggle />
				<LanguageToggle />
				<SettingsToggle />
			</div>
		</header>
	);
}

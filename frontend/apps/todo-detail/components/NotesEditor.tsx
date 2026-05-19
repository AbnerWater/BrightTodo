"use client";

import type { Editor } from "@tiptap/core";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import MarkdownIt from "markdown-it";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import TurndownService from "turndown";
import { SectionHeader } from "@/components/common/layout/SectionHeader";

interface NotesEditorProps {
	value: string;
	show: boolean;
	onToggle: () => void;
	onChange: (value: string) => void;
	onBlur?: () => void;
}

export function NotesEditor({
	value,
	show,
	onToggle,
	onChange,
	onBlur,
}: NotesEditorProps) {
	const t = useTranslations("todoDetail");
	const [isHovered, setIsHovered] = useState(false);
	const lastValueRef = useRef(value);

	const markdownParser = useMemo(
		() => new MarkdownIt({ breaks: true, linkify: true }),
		[],
	);
	const turndown = useMemo(() => {
		const service = new TurndownService({
			codeBlockStyle: "fenced",
			emDelimiter: "*",
		});
		service.keep(["del"]);
		return service;
	}, []);

	const editor = useEditor({
		immediatelyRender: false,
		extensions: [
			StarterKit,
			Placeholder.configure({
				placeholder: t("notesPlaceholder"),
				emptyEditorClass: "text-muted-foreground",
			}),
		],
		content: value ? markdownParser.render(value) : "",
		onUpdate: ({ editor }: { editor: Editor }) => {
			const html = editor.getHTML();
			const markdown = turndown.turndown(html);
			lastValueRef.current = markdown;
			onChange(markdown);
		},
		onBlur: () => {
			onBlur?.();
		},
		editorProps: {
			attributes: {
				class:
					"min-h-[140px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary",
			},
		},
	});

	useEffect(() => {
		if (!editor) return;
		if (value === lastValueRef.current) return;
		editor.commands.setContent(value ? markdownParser.render(value) : "", {
			emitUpdate: false,
		});
		lastValueRef.current = value;
	}, [editor, markdownParser, value]);

	return (
		<div
			role="group"
			className="mb-8"
			onMouseEnter={() => setIsHovered(true)}
			onMouseLeave={() => setIsHovered(false)}
		>
			<SectionHeader
				title={t("notesLabel")}
				show={show}
				onToggle={onToggle}
				headerClassName="mb-2"
				isHovered={isHovered}
			/>
			{show && (
				<div className="prose prose-sm max-w-none">
					<EditorContent editor={editor} />
				</div>
			)}
		</div>
	);
}

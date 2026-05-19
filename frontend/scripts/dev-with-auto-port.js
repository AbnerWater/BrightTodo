#!/usr/bin/env node
/**
 * 开发服务器启动脚本（支持动态端口探测）
 *
 * 功能：
 * 1. 自动探测可用的前端端口（默认从 3001 开始，避免与 Build 版冲突）
 * 2. 自动探测 FreeTodo 后端端口（通过 /health 端点验证是否是 FreeTodo 后端）
 * 3. 设置正确的环境变量并启动 Next.js 开发服务器
 *
 * 使用方法：
 *   pnpm dev          - 自动探测端口启动
 *   pnpm dev:backend  - 同时启动后端和前端（需要后端可执行文件）
 */

const { execSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

// 默认端口配置（开发版使用不同的默认端口，避免与 Build 版冲突）
const DEFAULT_FRONTEND_PORT = 3001;
const _DEFAULT_BACKEND_PORT = 8001;
const MAX_PORT_ATTEMPTS = 100;

function normalizePath(value) {
	const resolved = path.resolve(value);
	return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function isSymlinkedNodeModules() {
	const nodeModulesPath = path.join(process.cwd(), "node_modules");
	try {
		if (!fs.existsSync(nodeModulesPath)) {
			return false;
		}
		const stat = fs.lstatSync(nodeModulesPath);
		if (stat.isSymbolicLink()) {
			return true;
		}
		const realPath = fs.realpathSync(nodeModulesPath);
		return normalizePath(realPath) !== normalizePath(nodeModulesPath);
	} catch {
		return false;
	}
}

/**
 * 获取当前 Git Commit
 * @returns {string|null} - 完整 Commit Hash，获取失败则返回 null
 */
function getGitCommit() {
	const envCommit = process.env.FREETODO_GIT_COMMIT || process.env.GIT_COMMIT;
	if (envCommit) {
		return envCommit;
	}
	try {
		return execSync("git rev-parse HEAD", {
			stdio: ["ignore", "pipe", "ignore"],
		})
			.toString()
			.trim();
	} catch {
		return null;
	}
}

const FRONTEND_GIT_COMMIT = getGitCommit();

/**
 * 检查端口是否可用（同时检查 IPv4 和 IPv6）
 * @param {number} port - 要检查的端口
 * @returns {Promise<boolean>} - 端口是否可用
 */
function isPortAvailable(port) {
	return new Promise((resolve) => {
		const server = net.createServer();
		server.once("error", () => resolve(false));
		server.once("listening", () => {
			server.close();
			resolve(true);
		});
		// 使用 '::' 检查 IPv6（包含 IPv4），与 Next.js 默认行为一致
		// 如果系统不支持 IPv6，会自动回退到 IPv4
		server.listen(port, "::");
	});
}

/**
 * 查找可用端口
 * @param {number} startPort - 起始端口
 * @param {number} maxAttempts - 最大尝试次数
 * @returns {Promise<number>} - 可用的端口
 */
async function findAvailablePort(startPort, maxAttempts = MAX_PORT_ATTEMPTS) {
	for (let offset = 0; offset < maxAttempts; offset++) {
		const port = startPort + offset;
		if (await isPortAvailable(port)) {
			if (offset > 0) {
				console.log(`Port ${startPort} is in use, using port ${port}`);
			}
			return port;
		}
	}
	throw new Error(
		`Cannot find available port in range ${startPort}-${startPort + maxAttempts}`,
	);
}

/**
 * 检查指定端口是否运行着 FreeTodo 后端
 * 通过调用 /health 端点并验证 app 标识来确认是 FreeTodo 后端
 * @param {number} port - 后端端口
 * @returns {Promise<boolean>} - 是否是 FreeTodo 后端
 */
async function isFreeTodoBackend(port) {
	return new Promise((resolve) => {
		const req = http.get(
			{
				hostname: "127.0.0.1",
				port,
				path: "/health",
				timeout: 2000,
			},
			(res) => {
				let data = "";
				res.on("data", (chunk) => {
					data += chunk;
				});
				res.on("end", () => {
					try {
						const json = JSON.parse(data);
						// 验证是否是 FreeTodo/LifeTrace 后端
						// 只检查固定的应用标识字段
						if (json.app !== "lifetrace") {
							resolve(false);
							return;
						}

						const backendCommit =
							typeof json.git_commit === "string" ? json.git_commit : null;
						if (FRONTEND_GIT_COMMIT) {
							if (!backendCommit || backendCommit === "unknown") {
								resolve(false);
								return;
							}
							if (backendCommit !== FRONTEND_GIT_COMMIT) {
								console.log(
									`Skip backend at ${port}: git commit mismatch (${backendCommit})`,
								);
								resolve(false);
								return;
							}
						}

						resolve(true);
					} catch {
						resolve(false);
					}
				});
			},
		);

		req.on("error", () => resolve(false));
		req.on("timeout", () => {
			req.destroy();
			resolve(false);
		});
	});
}

/**
 * 查找运行中的 FreeTodo 后端端口
 * @returns {Promise<number|null>} - 运行中的 FreeTodo 后端端口，或 null
 */
async function findRunningBackendPort() {
	// 先检查开发版默认端口，然后是 Build 版默认端口
	const priorityPorts = [8001, 8000];
	for (const port of priorityPorts) {
		if (await isFreeTodoBackend(port)) {
			return port;
		}
	}
	// 再检查其他可能的端口（跳过已检查的）
	for (let port = 8002; port < 8100; port++) {
		if (await isFreeTodoBackend(port)) {
			return port;
		}
	}
	return null;
}

async function main() {
	console.log("Starting development server...\n");

	try {
		// 1. Find available frontend port
		// If PORT env var is set, use it (Electron main process may have allocated a port)
		let frontendPort;
		if (process.env.PORT) {
			frontendPort = Number.parseInt(process.env.PORT, 10);
			console.log(`Using frontend port from env: ${frontendPort}`);
		} else {
			frontendPort = await findAvailablePort(DEFAULT_FRONTEND_PORT);
			console.log(`Frontend port: ${frontendPort}`);
		}

		// 2. Find running FreeTodo backend port (verify via /health endpoint)
		console.log(`Searching for FreeTodo backend...`);
		if (FRONTEND_GIT_COMMIT) {
			console.log(`Frontend git commit: ${FRONTEND_GIT_COMMIT}`);
		}
		const backendPort = await findRunningBackendPort();
		if (backendPort) {
			console.log(`Detected FreeTodo backend running on port: ${backendPort}`);
		} else {
			const hint = "Start backend first - python -m lifetrace.server";
			const suffix = FRONTEND_GIT_COMMIT
				? ` (git commit: ${FRONTEND_GIT_COMMIT})`
				: "";
			throw new Error(
				`FreeTodo backend not detected via /health endpoint${suffix}. ${hint}`,
			);
		}

		const backendUrl = `http://localhost:${backendPort}`;
		console.log(`\nBackend API: ${backendUrl}`);
		console.log(`Frontend URL: http://localhost:${frontendPort}\n`);

		const disableTurbopack = isSymlinkedNodeModules();
		if (disableTurbopack && !process.env.NEXT_DISABLE_TURBOPACK) {
			console.log(
				"Detected symlinked node_modules, disabling Turbopack for compatibility.",
			);
		}

		const nextEnv = {
			...process.env,
			PORT: String(frontendPort),
			NEXT_PUBLIC_API_URL: backendUrl,
		};

		if (disableTurbopack && !("NEXT_DISABLE_TURBOPACK" in nextEnv)) {
			nextEnv.NEXT_DISABLE_TURBOPACK = "1";
		}

		// 3. 启动 Next.js 开发服务器
		const nextArgs = ["next", "dev", "--port", String(frontendPort)];
		if (disableTurbopack) {
			nextArgs.push("--webpack");
		}

		const nextProcess = spawn("pnpm", nextArgs, {
			stdio: "inherit",
			env: {
				...nextEnv,
			},
			shell: true,
		});

		// 处理进程信号
		process.on("SIGINT", () => {
			nextProcess.kill("SIGINT");
			process.exit(0);
		});

		process.on("SIGTERM", () => {
			nextProcess.kill("SIGTERM");
			process.exit(0);
		});

		nextProcess.on("exit", (code) => {
			process.exit(code || 0);
		});
	} catch (error) {
		console.error(`Failed to start: ${error.message}`);
		process.exit(1);
	}
}

main();

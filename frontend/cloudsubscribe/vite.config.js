import {defineConfig} from "vite";
import vue from "@vitejs/plugin-vue";
import federation from "@originjs/vite-plugin-federation";
import {resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {execSync} from "node:child_process";
import {readFileSync} from "node:fs";

const outputDir = resolve(
    fileURLToPath(new URL(".", import.meta.url)),
    "../../plugins.v2/cloudsubscribe/dist/assets",
);

// 动态读取后端真实版本号，避免前端写死
let pluginVersion = "1.5.0";
try {
    const initPyPath = resolve(
      fileURLToPath(new URL(".", import.meta.url)),
      "../../plugins.v2/cloudsubscribe/__init__.py",
    );
    const content = readFileSync(initPyPath, "utf-8");
    const match = content.match(/plugin_version\s*=\s*["']([^"']+)["']/);
    if (match && match[1]) {
        pluginVersion = match[1];
    }
} catch {
}

// 动态读取作者信息与 GitHub 仓库信息
let pluginAuthor = "odomu";
let authorUrl = "https://github.com/odomu";
let repoUrl = "https://github.com/odomu/MoviePilot-Plugins";
try {
    const initPyPath = resolve(
      fileURLToPath(new URL(".", import.meta.url)),
      "../../plugins.v2/cloudsubscribe/__init__.py",
    );
    const content = readFileSync(initPyPath, "utf-8");
    const authorMatch = content.match(/plugin_author\s*=\s*["']([^"']+)["']/);
    const urlMatch = content.match(/author_url\s*=\s*["']([^"']+)["']/);
    if (authorMatch && authorMatch[1]) pluginAuthor = authorMatch[1];
    if (urlMatch && urlMatch[1]) authorUrl = urlMatch[1];
} catch {
}

// 动态获取 Git Commit Short Hash 作为构建 ID
let buildId = "";
try {
    buildId = execSync("git rev-parse --short HEAD", {encoding: "utf-8"}).trim();
} catch {
    buildId = Date.now().toString(16).slice(-7);
}

// 动态获取构建日期与时间
const now = new Date();
const buildDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
const buildTime = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

export default defineConfig({
    base: "./",
    define: {
        __PLUGIN_VERSION__: JSON.stringify(pluginVersion),
        __PLUGIN_AUTHOR__: JSON.stringify(pluginAuthor),
        __AUTHOR_URL__: JSON.stringify(authorUrl),
        __REPO_URL__: JSON.stringify(repoUrl),
        __BUILD_DATE__: JSON.stringify(buildDate),
        __BUILD_TIME__: JSON.stringify(buildTime),
        __BUILD_ID__: JSON.stringify(buildId),
    },
    plugins: [
        vue(),
        federation({
            name: "cloudsubscribe",
            filename: "remoteEntry.js",
            exposes: {
                "./Page": "./src/components/Page.vue",
                "./Config": "./src/components/Config.vue",
                "./Dashboard": "./src/components/Dashboard.vue",
                "./AppPage": "./src/components/AppPage.vue",
                "./AppPageResource": "./src/components/AppPageResource.vue",
            },
            shared: {
                vue: {requiredVersion: false, generate: false},
                vuetify: {requiredVersion: false, generate: false, singleton: true},
                "vuetify/styles": {
                    requiredVersion: false,
                    generate: false,
                    singleton: true,
                },
            },
            format: "esm",
        }),
    ],
    build: {
        target: "esnext",
        minify: "esbuild",
        cssCodeSplit: true,
        emptyOutDir: true,
        outDir: outputDir,
        assetsDir: "",
    },
});

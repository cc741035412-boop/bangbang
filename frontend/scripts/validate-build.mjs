/**
 * 生产构建产物只读校验。
 *
 * 上线前跑一次：确认 dist/ 产出了完整可安装的 PWA 外壳（manifest、图标、
 * service worker、入口 HTML 引用的资源都在），并且没有把开发代理/开发入口
 * 漏进生产包。只读检查，不改任何文件；有问题以非零退出码失败。
 *
 * 用法：node scripts/validate-build.mjs   （构建完成后执行）
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const DIST = join(process.cwd(), "dist");
const errors = [];
const info = [];

function mustExist(rel) {
  if (!existsSync(join(DIST, rel))) errors.push(`缺少产物: ${rel}`);
}

// 1. 静态壳与 PWA 文件必须在
for (const file of [
  "index.html",
  "manifest.webmanifest",
  "sw.js",
  "icon-192.png",
  "icon-512.png",
  "icon-maskable-512.png",
]) {
  mustExist(file);
}

// 2. manifest 必须可解析且是可安装 PWA 的形态
try {
  const manifest = JSON.parse(readFileSync(join(DIST, "manifest.webmanifest"), "utf8"));
  if (manifest.display !== "standalone") errors.push("manifest.display 必须为 standalone");
  if (!Array.isArray(manifest.icons) || manifest.icons.length < 3) {
    errors.push("manifest 至少需要 3 个图标（192/512/maskable）");
  }
  if (!manifest.icons?.some((i) => i.purpose === "maskable")) {
    errors.push("manifest 需要 maskable 图标以满足安卓自适应图标要求");
  }
  if (!manifest.start_url || !manifest.scope) errors.push("manifest 需填写 start_url 与 scope");
  info.push("manifest 校验通过");
} catch (error) {
  errors.push(`manifest 解析失败: ${error.message}`);
}

// 3. index.html 必须声明 PWA 相关标签
try {
  const html = readFileSync(join(DIST, "index.html"), "utf8");
  if (!html.includes('rel="manifest"')) errors.push("index.html 缺少 manifest 声明");
  if (!html.includes('rel="apple-touch-icon"')) errors.push("index.html 缺少 apple-touch-icon");
  if (!html.includes("viewport-fit=cover")) errors.push("index.html 缺少 viewport-fit=cover（iPhone 安全区）");
  if (!html.includes('name="theme-color"')) errors.push("index.html 缺少 theme-color");

  // 4. HTML 引用的资产必须真实存在（剥掉 /assets/ 前缀）
  const assetRefs = [...html.matchAll(/\/assets\/[A-Za-z0-9._-]+/g)].map((m) => m[0]);
  for (const ref of assetRefs) {
    const rel = ref.replace(/^\//, "");
    if (!existsSync(join(DIST, rel))) errors.push(`index.html 引用了不存在的资产: ${rel}`);
  }
  info.push(`index.html 校验通过（${assetRefs.length} 个资产引用）`);
} catch (error) {
  errors.push(`index.html 读取失败: ${error.message}`);
}

// 5. 生产包不应包含 Vite 开发代理相关的占位（预防性提示）
const jsIndex = readFileSync(join(DIST, "index.html"), "utf8");
if (jsIndex.includes("VITE_API_PROXY_TARGET") || jsIndex.includes("127.0.0.1")) {
  errors.push("生产 HTML 里出现了开发代理/本机地址，请检查 vite.config 的 VITE_API_PROXY_TARGET");
}

if (errors.length) {
  console.error("❌ 生产构建校验失败：");
  for (const error of errors) console.error("   - " + error);
  process.exit(1);
}
console.log("✅ 生产构建校验通过");
for (const line of info) console.log("   " + line);

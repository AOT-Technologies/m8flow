import prefresh from "@prefresh/vite";
import { preactDevtoolsPlugin } from "./devtools.mjs";
import { createFilter, parseId } from "./utils.mjs";
import { vitePrerenderPlugin } from "vite-prerender-plugin";
import { transformAsync } from "@babel/core";
// @ts-ignore package doesn't ship with declaration files
import babelReactJsx from "@babel/plugin-transform-react-jsx";
// @ts-ignore package doesn't ship with declaration files
import babelReactJsxDev from "@babel/plugin-transform-react-jsx-development";
// @ts-ignore package doesn't ship with declaration files
import babelHookNames from "babel-plugin-transform-hook-names";
// Taken from https://github.com/vitejs/vite/blob/main/packages/plugin-react/src/index.ts
function preactPlugin({ devtoolsInProd, devToolsEnabled, prefreshEnabled, reactAliasesEnabled, prerender, include, exclude, babel, jsxImportSource, } = {}) {
    var _a;
    const baseParserOptions = [
        "importMeta",
        "explicitResourceManagement",
        "topLevelAwait",
    ];
    let config;
    let babelOptions = {
        babelrc: false,
        configFile: false,
        ...babel,
    };
    babelOptions.plugins || (babelOptions.plugins = []);
    babelOptions.presets || (babelOptions.presets = []);
    babelOptions.overrides || (babelOptions.overrides = []);
    babelOptions.parserOpts || (babelOptions.parserOpts = {});
    (_a = babelOptions.parserOpts).plugins || (_a.plugins = []);
    let useBabel = typeof babel !== "undefined";
    const shouldTransform = createFilter(include || [/\.[cm]?[tj]sx?$/], exclude || [/node_modules/]);
    devtoolsInProd = devtoolsInProd !== null && devtoolsInProd !== void 0 ? devtoolsInProd : false;
    prefreshEnabled = prefreshEnabled !== null && prefreshEnabled !== void 0 ? prefreshEnabled : true;
    reactAliasesEnabled = reactAliasesEnabled !== null && reactAliasesEnabled !== void 0 ? reactAliasesEnabled : true;
    prerender = prerender !== null && prerender !== void 0 ? prerender : { enabled: false };
    const prerenderPlugin = vitePrerenderPlugin(prerender);
    if (!prerender.previewMiddlewareEnabled) {
        const idx = prerenderPlugin.findIndex(p => p.name == "serve-prerendered-html");
        if (idx > -1) {
            prerenderPlugin.splice(idx, 1);
        }
    }
    const jsxPlugin = {
        name: "vite:preact-jsx",
        enforce: "pre",
        config() {
            return {
                build: {
                    rollupOptions: {
                        onwarn(warning, warn) {
                            // Silence Rollup's module-level directive warnings re:"use client".
                            // They're likely to come from `node_modules` and won't be actionable.
                            if (warning.code === "MODULE_LEVEL_DIRECTIVE" &&
                                warning.message.includes("use client"))
                                return;
                            // ESBuild seemingly doesn't include mappings for directives, causing
                            // Rollup to emit warnings about missing source locations. This too is
                            // likely to come from `node_modules` and won't be actionable.
                            // evanw/esbuild#3548
                            if (warning.code === "SOURCEMAP_ERROR" &&
                                warning.message.includes("resolve original location") &&
                                warning.pos === 0)
                                return;
                            warn(warning);
                        },
                    },
                },
                esbuild: useBabel
                    ? undefined
                    : {
                        jsx: "automatic",
                        jsxImportSource: jsxImportSource !== null && jsxImportSource !== void 0 ? jsxImportSource : "preact",
                    },
                optimizeDeps: {
                    include: ["preact", "preact/jsx-runtime", "preact/jsx-dev-runtime"],
                },
            };
        },
        configResolved(resolvedConfig) {
            config = resolvedConfig;
            devToolsEnabled =
                devToolsEnabled !== null && devToolsEnabled !== void 0 ? devToolsEnabled : (!config.isProduction || devtoolsInProd);
            useBabel || (useBabel = !config.isProduction || !!devToolsEnabled);
        },
        async transform(code, url) {
            // Ignore query parameters, as in Vue SFC virtual modules.
            const { id } = parseId(url);
            if (!useBabel || !shouldTransform(id))
                return;
            const parserPlugins = [
                ...baseParserOptions,
                "classProperties",
                "classPrivateProperties",
                "classPrivateMethods",
                !id.endsWith(".ts") && "jsx",
                /\.tsx?$/.test(id) && "typescript",
            ].filter(Boolean);
            const result = await transformAsync(code, {
                ...babelOptions,
                ast: true,
                root: config.root,
                filename: id,
                parserOpts: {
                    ...babelOptions.parserOpts,
                    sourceType: "module",
                    allowAwaitOutsideFunction: true,
                    plugins: parserPlugins,
                },
                generatorOpts: {
                    ...babelOptions.generatorOpts,
                    decoratorsBeforeExport: true,
                },
                plugins: [
                    ...babelOptions.plugins,
                    [
                        config.isProduction ? babelReactJsx : babelReactJsxDev,
                        {
                            runtime: "automatic",
                            importSource: jsxImportSource !== null && jsxImportSource !== void 0 ? jsxImportSource : "preact",
                        },
                    ],
                    ...(devToolsEnabled ? [babelHookNames] : []),
                ],
                sourceMaps: true,
                inputSourceMap: false,
            });
            // NOTE: Since no config file is being loaded, this path wouldn't occur.
            if (!result)
                return;
            return {
                code: result.code || code,
                map: result.map,
            };
        },
    };
    return [
        ...(reactAliasesEnabled
            ? [
                {
                    name: "preact:config",
                    config() {
                        return {
                            resolve: {
                                alias: {
                                    "react-dom/test-utils": "preact/test-utils",
                                    "react-dom": "preact/compat",
                                    react: "preact/compat",
                                },
                            },
                        };
                    },
                },
            ]
            : []),
        jsxPlugin,
        preactDevtoolsPlugin({
            devtoolsInProd,
            devToolsEnabled,
            shouldTransform,
        }),
        ...(prefreshEnabled
            ? [prefresh({ include, exclude, parserPlugins: baseParserOptions })]
            : []),
        ...(prerender.enabled ? prerenderPlugin : []),
    ];
}
export default preactPlugin;
export { preactPlugin as preact };

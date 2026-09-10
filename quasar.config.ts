// Configuration for your app
// https://v2.quasar.dev/quasar-cli-vite/quasar-config-file

import { defineConfig } from '#q-app/wrappers'
import { compression } from 'vite-plugin-compression2'
import dotenv from 'dotenv'

dotenv.config()

const ANALYZE = process.argv.includes('--analyze')

export default defineConfig(() => {
  return {
    // https://v2.quasar.dev/quasar-cli-vite/prefetch-feature
    // preFetch: true,

    // app boot file (/src/boot)
    // --> boot files are part of "main.js"
    // https://v2.quasar.dev/quasar-cli-vite/boot-files
    boot: [
      'unocss',
      'vue-query',
    ],

    // https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#css
    css: [
      // Resolved relative to src/css/, so climb out to src/styles/.
      '../styles/tokens.css',
      'app.scss',
    ],

    // https://github.com/quasarframework/quasar/tree/dev/extras
    extras: [
      // 'ionicons-v4',
      // 'mdi-v7',
      // 'fontawesome-v6',
      // 'eva-icons',
      // 'themify',
      // 'line-awesome',
      // 'roboto-font-latin-ext', // this or either 'roboto-font', NEVER both!

      'roboto-font', // optional, you are not bound to it
      // 'material-icons' // optional, you are not bound to it
    ],

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#build
    build: {
      target: {
        // Chrome 109 compatibility contract: the built app must run on
        // early-2023 Chromium.
        browser: ['chrome109'],
        node: 'node20',
      },

      typescript: {
        strict: false,
        vueShim: true,
        // extendTsConfig (tsConfig) {}
      },

      vueRouterMode: 'history', // available values: 'hash', 'history'
      // vueRouterBase,
      // vueDevtools,
      // vueOptionsAPI: false,

      // rebuildCache: true, // rebuilds Vite/linter/etc cache on startup

      // publicPath: '/',
      // analyze: true,
      // rawDefine: {}
      // ignorePublicFolder: true,
      // minify: false,
      // polyfillModulePreload: true,
      // distDir

      // extendViteConf (viteConf) {},
      // viteVuePluginOptions: {},
      sourcemap: ANALYZE ? 'hidden' : false,

      // The admin console is lazy-loaded but still part of this app. Give its
      // chunks and stylesheets their own directory so the PWA precache can
      // exclude them (see pwa.extendGenerateSWOptions below).
      extendViteConf (viteConf) {
        const output = viteConf.build?.rollupOptions?.output
        const baseOutput = Array.isArray(output) ? output[0] : output
        // Matches absolute module ids and root-relative asset names.
        const ADMIN_PATH = /(^|[\\/])src[\\/]admin[\\/]/
        // QTable is shared by several admin pages, so Rollup lifts it into its
        // own vendor-only chunk with no /src/admin/ module to match on.
        const ADMIN_ONLY_VENDOR = /[\\/]node_modules[\\/]quasar[\\/]src[\\/]components[\\/](?:table|markup-table)[\\/]/
        const isAdmin = (id: string) => ADMIN_PATH.test(id) || ADMIN_ONLY_VENDOR.test(id)
        viteConf.build = {
          ...(viteConf.build ?? {}),
          rollupOptions: {
            ...(viteConf.build?.rollupOptions ?? {}),
            output: {
              ...(baseOutput ?? {}),
              chunkFileNames: (chunk: { moduleIds: string[] }) =>
                chunk.moduleIds.some(isAdmin)
                  ? 'assets/admin/[name]-[hash].js'
                  : 'assets/[name]-[hash].js',
              // Admin page stylesheets are emitted beside their chunk, not into
              // the chunk directory, so route them too. Vite probes this hook
              // with no original file name when resolving CSS `url()` bases;
              // admin page CSS uses tokens only, so the fallback dir is unused.
              assetFileNames: (assetInfo: { originalFileNames?: string[], originalFileName?: string | null }) => {
                const origin = assetInfo.originalFileNames?.[0] ?? assetInfo.originalFileName ?? ''
                return isAdmin(origin)
                  ? 'assets/admin/[name]-[hash].[ext]'
                  : 'assets/[name]-[hash].[ext]'
              },
            },
          },
        }
      },

      vitePlugins: [
        ['vite-plugin-checker', {
          vueTsc: true,
          eslint: {
            lintCommand: 'eslint -c ./eslint.config.js "./src*/**/*.{ts,js,mjs,cjs,vue}"',
            useFlatConfig: true,
          },
        }, { server: false }],
        ['unocss/vite'],
        ...ANALYZE ? [['sonda/vite', { gzip: true, brotli: true }] as any] : [],
        compression(),
      ],
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#devserver
    devServer: {
      // https: true,
      open: false, // opens browser window automatically
      port: 9015,
      proxy: {
        '/api': {
          target: process.env.PYTHON_API_URL,
        },
      },
    },

    // https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#framework
    framework: {
      config: {
        // Brand primary comes from the accent token in src/styles/tokens.css.
        brand: {
          primary: '#0071e3',
        },
      },

      iconSet: 'material-symbols-outlined', // Quasar icon set
      lang: 'zh-CN', // Quasar language pack

      // For special cases outside of where the auto-import strategy can have an impact
      // (like functional components as one of the examples),
      // you can manually specify Quasar components/directives to be available everywhere:
      //
      // components: [],
      // directives: [],

      // Quasar plugins
      plugins: [
        'Notify',
        'Dark',
        'Dialog',
        'LocalStorage',
      ],
    },

    // animations: 'all', // --- includes all animations
    // https://v2.quasar.dev/options/animations
    animations: [],

    // https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#sourcefiles
    // sourceFiles: {
    //   rootComponent: 'src/App.vue',
    //   router: 'src/router/index',
    //   store: 'src/store/index',
    //   pwaRegisterServiceWorker: 'src-pwa/register-service-worker',
    //   pwaServiceWorker: 'src-pwa/custom-service-worker',
    //   pwaManifestFile: 'src-pwa/manifest.json',
    //   electronMain: 'src-electron/electron-main',
    //   electronPreload: 'src-electron/electron-preload'
    //   bexManifestFile: 'src-bex/manifest.json
    // },

    // https://v2.quasar.dev/quasar-cli-vite/developing-ssr/configuring-ssr
    ssr: {
      prodPort: 3000, // The default port that the production server should use
      // (gets superseded if process.env.PORT is specified at runtime)

      middlewares: [
        'render', // keep this as last one
      ],

      // extendPackageJson (json) {},
      // extendSSRWebserverConf (esbuildConf) {},

      // manualStoreSerialization: true,
      // manualStoreSsrContextInjection: true,
      // manualStoreHydration: true,
      // manualPostHydrationTrigger: true,

      pwa: false,
      // pwaOfflineHtmlFilename: 'offline.html', // do NOT use index.html as name!

      // pwaExtendGenerateSWOptions (cfg) {},
      // pwaExtendInjectManifestOptions (cfg) {}
    },

    // https://v2.quasar.dev/quasar-cli-vite/developing-pwa/configuring-pwa
    pwa: {
      workboxMode: 'GenerateSW', // 'GenerateSW' or 'InjectManifest'
      // swFilename: 'sw.js',
      // manifestFilename: 'manifest.json',
      // extendManifestJson (json) {},
      // useCredentialsForManifestTag: true,
      // injectPwaMetaTags: false,
      // extendPWACustomSWConf (esbuildConf) {},
      extendGenerateSWOptions (cfg) {
        cfg.globPatterns = ['**/*.{js,css,html,ico,png,svg,woff2}']
        // Lazy admin chunks must not be precached for end users.
        cfg.globIgnores = ['**/assets/admin/**']
        cfg.navigateFallbackDenylist = [
          /^\/api\//,
          /^\/oauth(?:\/|$)/,
          /^\/\.well-known(?:\/|$)/,
          /^\/mcp(?:\/|$)/,
        ]
        cfg.skipWaiting = false
        cfg.clientsClaim = true
      },
      // extendInjectManifestOptions (cfg) {}
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-cordova-apps/configuring-cordova
    cordova: {
      // noIosLegacyBuildFlag: true, // uncomment only if you know what you are doing
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-capacitor-apps/configuring-capacitor
    capacitor: {
      hideSplashscreen: true,
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-electron-apps/configuring-electron
    electron: {
      // extendElectronMainConf (esbuildConf) {},
      // extendElectronPreloadConf (esbuildConf) {},

      // extendPackageJson (json) {},

      // Electron preload scripts (if any) from /src-electron, WITHOUT file extension
      preloadScripts: ['electron-preload'],

      // specify the debugging port to use for the Electron app when running in development mode
      inspectPort: 5858,

      bundler: 'packager', // 'packager' or 'builder'

      packager: {
        // https://github.com/electron-userland/electron-packager/blob/master/docs/api.md#options

        // OS X / Mac App Store
        // appBundleId: '',
        // appCategoryType: '',
        // osxSign: '',
        // protocol: 'myapp://path',

        // Windows only
        // win32metadata: { ... }
      },

      builder: {
        // https://www.electron.build/configuration/configuration

        appId: 'nyaai',
      },
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-browser-extensions/configuring-bex
    bex: {
      // extendBexScriptsConf (esbuildConf) {},
      // extendBexManifestJson (json) {},

      /**
       * The list of extra scripts (js/ts) not in your bex manifest that you want to
       * compile and use in your browser extension. Maybe dynamic use them?
       *
       * Each entry in the list should be a relative filename to /src-bex/
       *
       * @example [ 'my-script.ts', 'sub-folder/my-other-script.js' ]
       */
      extraScripts: [],
    },
  }
})

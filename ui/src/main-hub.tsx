import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import './index.css'
import './shared/uiScale' // side-effect: 加载即应用持久显示缩放(4K/高 DPI)
import App from './shared/App.tsx'
import { LangProvider } from './shared/i18n.tsx'
import { AuthProvider } from './shared/auth.tsx'
import { LandingPage } from './hub/LandingPage.tsx'
import { CatalogPage } from './hub/CatalogPage.tsx'
import { DetailPage } from './hub/DetailPage.tsx'
import { HubPrePlay } from './hub/HubPrePlay.tsx'
import { HubStagePage } from './hub/HubStagePage.tsx'
import { SignupPage } from './hub/SignupPage.tsx'
import { AccountPage } from './hub/AccountPage.tsx'
import { ManagePage } from './hub/ManagePage.tsx'
import { PricingPage } from './hub/PricingPage.tsx'
import { AdminPage } from './hub/AdminPage.tsx'
import { AdminDashboardPage } from './hub/AdminDashboardPage.tsx'
// ── 同源化(HUB-GOLIVE §P1.5,niko:创作/Soul Talk 全换 local 的东西;
// 且 Remote 不出现 /local 命名空间)──
// hub 入口装载 LocalShell 的创作门/工坊/资料/PrePlay/stage,挂在 hub
// 原生路径(/create /studio /library /play/prep /play/stage);
// localClient 基址指沙盒路由的 /engine 直通面 —— 组件零分叉。
import { setLocalApiBase } from './local/localClient.ts'
import { LocalApp } from './local/LocalApp.tsx'
import { LocalPrePlay } from './play/LocalPrePlay.tsx'
import { PlayStage } from './play/stage/PlayStage.tsx'
import { LocalCreateGate } from './local/LocalCreateGate.tsx'
import { LocalStudio } from './local/LocalStudio.tsx'
import { SoulStudio } from './local/SoulStudio.tsx'
import { LocalLibrary } from './local/LocalLibrary.tsx'
import { HostedChromeContext } from './local/hostedChrome.tsx'
import { StageBackendProvider, makeEngineBackend } from './play/stage/backend.ts'
import { computeOrigin } from './play/playClient.ts'

// 全入口生效:local API 经沙盒路由直通账户引擎。Hub/Compute 分层部署时
// (HUB-GOLIVE §P2:页面在 CloudFront,API 在 compute 域)computeOrigin()
// 为显式 origin;同源部署(本地栈/wheel)为 ''。
setLocalApiBase(`${computeOrigin()}/api/v1/play/engine`)

// hosted 引擎面 stage 后端(caps 全开 —— 引擎原生 /traces /rollback)。
const hostedEngine = makeEngineBackend(`${computeOrigin()}/api/v1/play/engine`, 'hosted')

/** LocalShell 组件的 hosted 外壳:hosted chrome(头部导航切 hub 语义、
 *  设置隐藏)+ hosted 引擎后端。 */
function HostedShell() {
  return (
    <HostedChromeContext.Provider value={true}>
      <StageBackendProvider value={hostedEngine}>
        <LocalApp />
      </StageBackendProvider>
    </HostedChromeContext.Provider>
  )
}

/** legacy /local/* → hub 原生路径(组件内部仍有 '/local/...' 的编程式
 *  跳转与硬跳转 —— 一律重定向到原生 URL,query 原样保留)。 */
const LEGACY_MAP: [string, string][] = [
  ['/local/create/studio', '/studio'],
  ['/local/create/soul', '/studio/soul'],
  ['/local/create', '/create'],
  ['/local/library', '/library'],
  ['/local/preplay/', '/play/prep/'],
  ['/local/stage', '/play/stage'],
  ['/local/play', '/worlds'],
  ['/local', '/'],
]

function LegacyLocalRedirect() {
  const loc = useLocation()
  const p = loc.pathname
  for (const [from, to] of LEGACY_MAP) {
    if (p === from || p.startsWith(from)) {
      const rest = p.slice(from.length)
      return <Navigate to={`${to}${rest}${loc.search}`} replace />
    }
  }
  return <Navigate to="/" replace />
}

// Hub entry (dist-hub) — the storefront (public catalog + accounts) plus
// the shared play kernel AND the LocalShell creation/library pages mounted
// against the account sandbox at hub-NATIVE paths (同源化;Remote 没有
// /local). This dist deploys via deploy-web.sh.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <LangProvider>
        <AuthProvider>
          <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<LandingPage />} />
          <Route path="worlds" element={<CatalogPage kind="worlds" />} />
          <Route path="worlds/:slug" element={<DetailPage kind="worlds" />} />
          <Route path="souls" element={<CatalogPage kind="souls" />} />
          <Route path="souls/:slug" element={<DetailPage kind="souls" />} />
          <Route path="play/:kind/:slug" element={<HubPrePlay />} />
          <Route path="play/session/:sid" element={<HubStagePage />} />
          <Route path="signup" element={<SignupPage />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="manage/:kind/:slug" element={<ManagePage />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="admin/dashboard" element={<AdminDashboardPage />} />
          {/* LocalShell 复用面 · hub 原生路径(老 hub CreatePage 已删,
              创作=账户沙盒里的同一套工坊)。/play/prep 静态段优先于
              /play/:kind/:slug 动态段(react-router 按特异度排序)。
              C9(niko):chrome 属于壳 —— 复用面嵌在 App 布局内,顶栏
              永远是 Hub 的 Header;LocalApp 在 hosted 下不渲染自己的头。 */}
          <Route element={<HostedShell />}>
            <Route path="create" element={<LocalCreateGate />} />
            <Route path="studio" element={<LocalStudio />} />
            <Route path="studio/soul" element={<SoulStudio />} />
            <Route path="library" element={<LocalLibrary />} />
            <Route path="play/prep/:slug" element={<LocalPrePlay />} />
            <Route path="play/stage" element={<PlayStage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
        {/* legacy /local/* —— 组件内部残留的 '/local/...' 跳转统一翻译 */}
        <Route path="/local/*" element={<LegacyLocalRedirect />} />
        <Route path="/local" element={<LegacyLocalRedirect />} />
          </Routes>
        </AuthProvider>
      </LangProvider>
    </BrowserRouter>
  </StrictMode>,
)

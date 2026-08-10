import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import './shared/uiScale' // side-effect: 加载即应用持久显示缩放(4K/高 DPI)
import { LangProvider } from './shared/i18n.tsx'
import { AuthProvider } from './shared/auth.tsx'
import { LocalApp } from './local/LocalApp.tsx'
import { LocalWelcome } from './local/LocalWelcome.tsx'
import { LocalHome } from './local/LocalHome.tsx'
import { LocalPlayGate } from './local/LocalPlayGate.tsx'
import { LocalPrePlay } from './play/LocalPrePlay.tsx'
import { PlayStage } from './play/stage/PlayStage.tsx'
import { LocalWorldDetail } from './local/LocalWorldDetail.tsx'
import { LocalCreateGate } from './local/LocalCreateGate.tsx'
import { LocalStudio } from './local/LocalStudio.tsx'
import { SoulStudio } from './local/SoulStudio.tsx'
import { LocalSettings } from './local/LocalSettings.tsx'
import { ObservatoryShell } from './local/ObservatoryShell.tsx'
import { LocalLibrary } from './local/LocalLibrary.tsx'

// LocalShell entry (dist-local) — the study (local pages) + the shared
// play kernel. No Hub storefront pages are bundled. This dist is what
// sync_play_ui.sh vendors into the wheel and the desktop shell packages
// (PLAY-FUSION-DECISIONS.md D10 — one dist, engine + shell identical).
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <LangProvider>
        <AuthProvider>
          <Routes>
        {/* LocalShell — the local engine's own chrome (no Hub header/auth
            gate); pages talk to `neonrp web` via localClient. */}
        {/* 游戏门面(标题画面)— 全屏、LocalApp chrome 之外 */}
        <Route path="/local/welcome" element={<LocalWelcome />} />
        <Route path="/local" element={<LocalApp />}>
          <Route index element={<LocalHome />} />
          <Route path="play" element={<LocalPlayGate />} />
          <Route path="play/:worldId" element={<LocalWorldDetail />} />
          <Route path="preplay/:slug" element={<LocalPrePlay />} />
          {/* 游玩现场(D5)+ 开机剧场(D7)— 经典 neonrp web 页的内容架构在
              SPA 里重生。挂在 LocalApp 下,继承 --lc-* 主题 token;PlayStage
              自身 position:fixed 全屏铺满。桥接切换(PrePlay→这里)由主线接。 */}
          <Route path="stage" element={<PlayStage />} />
          <Route path="create" element={<LocalCreateGate />} />
          <Route path="create/studio" element={<LocalStudio />} />
          <Route path="create/soul" element={<SoulStudio />} />
          <Route path="library" element={<LocalLibrary />} />
          <Route path="settings" element={<LocalSettings />} />
          {/* C1 观察窗(四页面新 UI 起点)—— Web=看活世界的窗 */}
          <Route path="observe" element={<ObservatoryShell />} />
        </Route>
        {/* 旧 Hub 血统 PlayPage 已从 local 入口卸载(niko:stage 拥有整个
            游玩会话,local 流不许回落旧表面)。任何游离路径一律回书房;
            hub 目录流的 PlayPage 只活在 main-hub 入口里。 */}
        <Route path="/" element={<Navigate to="/local" replace />} />
        <Route path="*" element={<Navigate to="/local" replace />} />
          </Routes>
        </AuthProvider>
      </LangProvider>
    </BrowserRouter>
  </StrictMode>,
)

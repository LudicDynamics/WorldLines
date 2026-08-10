import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Footer } from './Footer'
import { RegistrationGate } from './RegistrationGate'

export default function App() {
  return (
    <div className="flex flex-col min-h-full w-full max-w-[1440px] mx-auto bg-[var(--color-bg)]">
      <Header />
      {/* One-time account setup (handle + password) — site-wide gate. */}
      <RegistrationGate />
      <main
        className="flex flex-col items-center w-full"
        style={{ paddingTop: 'var(--section-top-offset)' }}
      >
        <Outlet />
        <Footer />
      </main>
    </div>
  )
}
